import math
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import pytz

class SkillAnalyzer:
    def __init__(self):
        self.mod_multipliers = {
            'HD': 1.06,
            'HR': 1.12,
            'DT': 1.18,
            'EZ': 0.88,
            'FL': 1.15,
            'SO': 0.92,
            'NF': 0.98,
            'SD': 1.0,
            'PF': 1.0,
            'NC': 1.18,  # Same as DT
            'HT': 0.82
        }
        
        # More reasonable minimum data requirements
        self.min_recent_plays = 6   # Reduced from 8
        self.min_top_plays = 8      # Reduced from 12
        self.min_confidence_threshold = 20  # Reduced from 25

    def validate_play_data(self, play: Dict) -> bool:
        """Validate that a play has the required data for analysis"""
        required_fields = ['accuracy', 'created_at']
        
        # Check main play fields
        for field in required_fields:
            if not play.get(field):
                return False
        
        # Check beatmap data
        beatmap_full = play.get('beatmap_full', {})
        if not beatmap_full:
            return False
            
        # Required beatmap fields
        beatmap_fields = ['difficulty_rating', 'ar', 'bpm']
        for field in beatmap_fields:
            if beatmap_full.get(field) is None:
                return False
        
        # Validate ranges
        accuracy = play.get('accuracy', 0)
        if not (0 <= accuracy <= 1):
            return False
        
        star_rating = beatmap_full.get('difficulty_rating', 0)
        if not (0 <= star_rating <= 12):
            return False
            
        ar = beatmap_full.get('ar', 0)
        if not (0 <= ar <= 11):
            return False
            
        bpm = beatmap_full.get('bpm', 0)
        if not (30 <= bpm <= 600):
            return False
        
        return True

    def filter_valid_plays(self, plays: List[Dict]) -> List[Dict]:
        """Filter plays to only include those with valid data"""
        return [play for play in plays if self.validate_play_data(play)]

    def calculate_skill_components(self, play: Dict) -> Tuple[float, float, float]:
        """Calculate aim, speed, and accuracy skill components - improved balance"""
        beatmap = play.get('beatmap_full', {})
        accuracy = play.get('accuracy', 0) * 100
        star_rating = beatmap.get('difficulty_rating', 0)
        ar = beatmap.get('ar', 9)
        bpm = beatmap.get('bpm', 120)
        passed = play.get('passed', True)
        
        # Improved accuracy scaling - more rewarding for high accuracy
        if accuracy >= 98:
            acc_factor = 0.98 + (accuracy - 98) * 0.02  # 0.98 to 1.0 for 98-100%
        elif accuracy >= 95:
            acc_factor = 0.95 + (accuracy - 95) * 0.01  # 0.95 to 0.98 for 95-98%
        elif accuracy >= 90:
            acc_factor = 0.90 + (accuracy - 90) * 0.01  # 0.90 to 0.95 for 90-95%
        else:
            acc_factor = accuracy / 100
        
        # Reasonable penalty for failed plays
        fail_penalty = 0.85 if not passed else 1.0

        # Improved difficulty scaling - more realistic progression
        if star_rating <= 2.0:
            difficulty_scale = 0.8 + (star_rating / 2.0) * 0.2  # 0.8 to 1.0
        elif star_rating <= 4.0:
            difficulty_scale = 1.0 + (star_rating - 2.0) * 0.2  # 1.0 to 1.4
        elif star_rating <= 6.0:
            difficulty_scale = 1.4 + (star_rating - 4.0) * 0.25  # 1.4 to 1.9
        else:
            difficulty_scale = 1.9 + (star_rating - 6.0) * 0.15  # 1.9+ for 6+ stars
        
        # Improved skill calculations
        # Aim skill - considers star rating and AR
        aim_skill = acc_factor * (star_rating ** 1.05) * (1 + (ar - 9) * 0.05) * difficulty_scale
        
        # Speed skill - considers BPM and star rating
        bpm_factor = min(bpm / 150, 2.0)  # Normalize BPM, cap at 2x multiplier
        speed_skill = acc_factor * bpm_factor * (star_rating ** 0.8) * difficulty_scale
        
        # Accuracy skill - rewards precision, especially at higher difficulties
        if accuracy > 90:
            accuracy_base = ((accuracy - 90) / 10) ** 1.1
            accuracy_skill = accuracy_base * (1 + star_rating * 0.1)
        else:
            accuracy_skill = 0

        return aim_skill * fail_penalty, speed_skill * fail_penalty, accuracy_skill * fail_penalty

    def get_mod_multiplier(self, mods: List[str]) -> float:
        """Calculate mod multiplier for a play - fixed double application bug"""
        if not mods:
            return 1.0
            
        # Handle mod combinations properly - no double application
        has_dt = 'DT' in mods or 'NC' in mods
        has_hr = 'HR' in mods
        has_hd = 'HD' in mods
        has_ez = 'EZ' in mods
        has_fl = 'FL' in mods
        has_ht = 'HT' in mods
        
        # Start with base multiplier
        multiplier = 1.0
        
        # Apply combination bonuses (these override individual mod multipliers)
        if has_dt and has_hr and has_hd:
            multiplier *= 1.35  # DTHRHD
        elif has_dt and has_hr:
            multiplier *= 1.28  # DTHR
        elif has_dt and has_hd:
            multiplier *= 1.24  # DTHD
        elif has_hr and has_hd:
            multiplier *= 1.18  # HRHD
        else:
            # Apply individual mod multipliers only if no combinations
            if has_dt:
                multiplier *= self.mod_multipliers['DT']
            if has_hr:
                multiplier *= self.mod_multipliers['HR']
            if has_hd:
                multiplier *= self.mod_multipliers['HD']
        
        # Apply other mods that don't have combinations
        if has_ez:
            multiplier *= self.mod_multipliers['EZ']
        if has_fl:
            multiplier *= self.mod_multipliers['FL']
        if has_ht:
            multiplier *= self.mod_multipliers['HT']
        
        # Apply other single mods
        for mod in mods:
            if mod in ['SO', 'NF', 'SD', 'PF'] and mod in self.mod_multipliers:
                multiplier *= self.mod_multipliers[mod]
        
        # Reasonable multiplier range
        return min(max(multiplier, 0.6), 2.5)

    def calculate_skill_score(self, play: Dict) -> float:
        """Calculate overall skill score for a play"""
        aim, speed, accuracy = self.calculate_skill_components(play)
        mods = play.get('mods', [])
        mod_multiplier = self.get_mod_multiplier(mods)
        
        # Balanced weighting
        base_score = (0.45 * aim + 0.35 * speed + 0.20 * accuracy)
        return base_score * mod_multiplier

    def calculate_temporal_weight(self, play_date: str) -> float:
        """Calculate temporal weight - fixed timezone issues"""
        try:
            # Parse datetime properly
            play_datetime = datetime.fromisoformat(play_date.replace('Z', '+00:00'))
            
            # Convert to UTC for consistent comparison
            if play_datetime.tzinfo is None:
                play_datetime = play_datetime.replace(tzinfo=pytz.UTC)
            
            current_time = datetime.now(pytz.UTC)
            days_old = (current_time - play_datetime).days
            
            # Gradual decay
            if days_old <= 14:
                return 1.0
            elif days_old <= 30:
                return 0.95
            elif days_old <= 60:
                return 0.85
            elif days_old <= 90:
                return 0.75
            elif days_old <= 180:
                return 0.6
            else:
                return max(0.4, math.exp(-0.005 * days_old))
        except:
            return 0.5

    def detect_retries(self, plays: List[Dict]) -> List[Dict]:
        """Detect and mark retry attempts"""
        if not plays:
            return []
            
        plays_with_retries = []
        
        for i, play in enumerate(plays):
            play_copy = play.copy()
            play_copy['is_retry'] = False
            
            current_time = play.get('created_at')
            beatmap_id = play.get('beatmap', {}).get('id')
            
            if current_time and beatmap_id:
                try:
                    current_datetime = datetime.fromisoformat(current_time.replace('Z', '+00:00'))
                    
                    # Check previous plays within 20 minutes
                    for j in range(max(0, i-8), i):
                        prev_play = plays[j]
                        prev_time = prev_play.get('created_at')
                        prev_beatmap_id = prev_play.get('beatmap', {}).get('id')
                        
                        if prev_time and prev_beatmap_id == beatmap_id:
                            prev_datetime = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))
                            time_diff = abs((current_datetime - prev_datetime).total_seconds())
                            
                            if time_diff < 1200:  # 20 minutes
                                play_copy['is_retry'] = True
                                break
                except:
                    pass
                    
            plays_with_retries.append(play_copy)
        
        return plays_with_retries

    def calculate_weighted_average(self, plays: List[Dict]) -> float:
        """Calculate weighted average skill score"""
        if not plays:
            return 0.0
        
        valid_plays = self.filter_valid_plays(plays)
        if not valid_plays:
            return 0.0
            
        plays_with_retries = self.detect_retries(valid_plays)
        
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for i, play in enumerate(plays_with_retries):
            skill_score = self.calculate_skill_score(play)
            temporal_weight = self.calculate_temporal_weight(play.get('created_at', ''))
            
            # Gradual position decay
            position_weight = 0.97 ** i
            
            # Reasonable retry penalty
            retry_penalty = 0.75 if play.get('is_retry', False) else 1.0
            
            final_weight = temporal_weight * position_weight * retry_penalty
            total_weighted_score += skill_score * final_weight
            total_weight += final_weight
        
        return total_weighted_score / total_weight if total_weight > 0 else 0.0

    def calculate_recent_skill(self, recent_plays: List[Dict]) -> float:
        """Calculate recent skill level"""
        if not recent_plays:
            return 0.0
        
        # Use up to 30 recent plays for good balance
        return self.calculate_weighted_average(recent_plays[:30])

    def calculate_peak_skill(self, top_plays: List[Dict]) -> float:
        """Calculate peak skill level"""
        if not top_plays:
            return 0.0
        
        # Use top 25 plays by PP
        top_plays_sorted = sorted(top_plays, key=lambda x: x.get('pp', 0), reverse=True)[:25]
        return self.calculate_weighted_average(top_plays_sorted)

    def calculate_skill_match(self, recent_skill: float, peak_skill: float, recent_count: int) -> float:
        """Calculate skill match percentage"""
        if peak_skill == 0:
            return 0.0
        
        match = (recent_skill / peak_skill) * 100
        
        # Improved reliability scaling
        if recent_count >= 25:
            reliability = 1.0
        elif recent_count >= 15:
            reliability = 0.95 + (recent_count - 15) * 0.005
        elif recent_count >= 10:
            reliability = 0.85 + (recent_count - 10) * 0.02
        elif recent_count >= 6:
            reliability = 0.7 + (recent_count - 6) * 0.0375
        else:
            reliability = max(0.5, recent_count * 0.1)
        
        return round(match * reliability, 2)

    def calculate_confidence_factors(self, recent_plays: List[Dict]) -> Dict[str, float]:
        """Calculate confidence factors - improved scaling"""
        if not recent_plays:
            return {'volume': 0, 'diversity': 0, 'recency': 0, 'consistency': 0}
        
        valid_plays = self.filter_valid_plays(recent_plays)
        
        # Volume factor - more gradual and less harsh
        play_count = len(valid_plays)
        if play_count >= 25:
            volume = 1.0
        elif play_count >= 15:
            volume = 0.85 + (play_count - 15) * 0.015
        elif play_count >= 10:
            volume = 0.7 + (play_count - 10) * 0.03
        elif play_count >= 6:
            volume = 0.5 + (play_count - 6) * 0.05
        else:
            volume = max(0.3, play_count * 0.08)
        
        # Diversity factor - more reasonable requirements
        unique_maps = len(set(
            play.get('beatmap', {}).get('id') 
            for play in valid_plays 
            if play.get('beatmap', {}).get('id')
        ))
        
        if unique_maps >= 15:
            diversity = 1.0
        elif unique_maps >= 10:
            diversity = 0.8 + (unique_maps - 10) * 0.04
        elif unique_maps >= 6:
            diversity = 0.6 + (unique_maps - 6) * 0.05
        else:
            diversity = max(0.4, unique_maps * 0.1)
        
        # Recency factor - spread across weeks
        try:
            play_weeks = set()
            for play in valid_plays:
                if play.get('created_at'):
                    play_date = datetime.fromisoformat(play['created_at'].replace('Z', '+00:00'))
                    play_weeks.add(play_date.isocalendar()[1])
            
            week_count = len(play_weeks)
            if week_count >= 6:
                recency = 1.0
            elif week_count >= 4:
                recency = 0.8 + (week_count - 4) * 0.1
            elif week_count >= 2:
                recency = 0.6 + (week_count - 2) * 0.1
            else:
                recency = max(0.4, week_count * 0.3)
        except:
            recency = 0.5
        
        # Consistency factor - less harsh on accuracy variation
        try:
            accuracies = [play.get('accuracy', 0) * 100 for play in valid_plays]
            if len(accuracies) > 1:
                acc_std = statistics.stdev(accuracies)
                # More forgiving accuracy consistency
                consistency = max(0.4, 1 - (acc_std / 25))
            else:
                consistency = 0.8
        except:
            consistency = 0.6
        
        return {
            'volume': volume,
            'diversity': diversity,
            'recency': recency,
            'consistency': consistency
        }

    def calculate_confidence_score(self, factors: Dict[str, float]) -> float:
        """Calculate overall confidence score"""
        weights = {
            'volume': 0.35,
            'diversity': 0.25,
            'recency': 0.25,
            'consistency': 0.15
        }

        confidence = sum(
            factors.get(factor, 0) * weight 
            for factor, weight in weights.items()
        )

        # Scale to percentage
        confidence = min(confidence * 100, 100.0)

        # Less harsh volume penalties
        volume = factors.get("volume", 0)
        if volume < 0.4:
            confidence *= 0.75
        elif volume < 0.6:
            confidence *= 0.9

        return round(confidence, 1)

    def determine_verdict(self, skill_match: float, confidence: float,
                        valid_recent_plays: List[Dict], valid_top_plays: List[Dict]) -> str:
        """Determine overall verdict with improved logic"""
        
        # Check for insufficient data - more lenient
# Check if user has no recent plays but valid top plays → inactive
        if len(valid_recent_plays) == 0 and len(valid_top_plays) >= self.min_top_plays:
            return 'inactive'

        # Check for insufficient data
        if len(valid_recent_plays) < self.min_recent_plays or len(valid_top_plays) < self.min_top_plays:
            return 'insufficient'


        # More reasonable confidence requirements
        if confidence < self.min_confidence_threshold:
            # Allow lower confidence if skill match is reasonable
            if confidence >= 15 and skill_match >= 50:
                pass  # proceed to verdict logic
            else:
                return 'insufficient'

        # Verdict thresholds (kept reasonable)
        skill_match = round(skill_match, 1)

        if skill_match >= 92:
            return 'accurate'
        elif skill_match >= 75:
            return 'slightly_rusty'
        elif skill_match >= 55:
            return 'rusty'
        elif skill_match >= 35:
            return 'overranked'
        else:
            return 'inactive'

    def generate_insights(self, valid_recent_plays: List[Dict], valid_top_plays: List[Dict]) -> List[str]:
        """Generate insights about the player's performance"""
        insights = []

        if not valid_top_plays or not valid_recent_plays:
            insights.append("Limited data available for comprehensive analysis")
            return insights

        # --- Insight 1: Top play age ---
        nine_months_ago = datetime.now(pytz.UTC) - timedelta(days=270)
        old_top_plays = sum(
            1 for play in valid_top_plays[:10]
            if 'created_at' in play and datetime.fromisoformat(play['created_at'].replace('Z', '+00:00')) < nine_months_ago
        )
        if old_top_plays > 7:
            insights.append("Most top plays are quite old - consider setting new personal bests")

        # --- Insight 2: Star rating gap (recent vs top) ---
        if len(valid_top_plays) >= 5 and len(valid_recent_plays) >= 5:
            avg_top_sr = sum(p.get('beatmap_full', {}).get('difficulty_rating', 0) for p in valid_top_plays[:10]) / 10
            avg_recent_sr = sum(p.get('beatmap_full', {}).get('difficulty_rating', 0) for p in valid_recent_plays[:10]) / 10

            if avg_recent_sr < avg_top_sr * 0.7:
                insights.append("Recent plays are significantly easier than your peak performance")
            elif avg_recent_sr > avg_top_sr * 1.15:
                insights.append("You're attempting harder maps than your current top plays")

        # --- Insight 3: Accuracy consistency & quality ---
        if len(valid_recent_plays) > 6:
            accuracies = [p.get('accuracy', 0) * 100 for p in valid_recent_plays]
            if len(accuracies) > 1:
                acc_std = statistics.stdev(accuracies)
                avg_acc = statistics.mean(accuracies)
                if acc_std < 5:
                    if avg_acc >= 95:
                        insights.append("Excellent aim consistency with exceptional accuracy!")
                    elif avg_acc >= 90:
                        insights.append("Strong aim consistency with good accuracy")
                    elif avg_acc >= 75:
                        insights.append("Consistent aim, but accuracy needs improvement")
                    else:
                        insights.append("Very consistent, but accuracy is too low — focus on precision")


        # --- Insight 4: Retry behavior ---
        plays_with_retries = self.detect_retries(valid_recent_plays)
        retry_count = sum(1 for play in plays_with_retries if play.get('is_retry', False))
        retry_rate = retry_count / len(plays_with_retries) if plays_with_retries else 0

        if retry_rate > 0.4:
            insights.append("High retry rate detected - consider focusing on first-try consistency")
        elif retry_rate < 0.15:
            insights.append("Good play selection - low retry rate shows consistency")

        # --- Insight 5: Mod variety ---
        mod_usage = {}
        for play in valid_recent_plays:
            mods = play.get('mods', [])
            mod_key = '+'.join(sorted(mods)) if mods else 'NM'
            mod_usage[mod_key] = mod_usage.get(mod_key, 0) + 1

        if len(mod_usage) == 1:
            insights.append("Consider trying different mods to develop diverse skills")
        elif len(mod_usage) > 4:
            insights.append("Good mod variety - you're developing well-rounded skills")

        # --- Insight 6: Speed vs Aim bias ---
        if len(valid_recent_plays) >= 5:
            aim_skills = [self.calculate_skill_components(p)[0] for p in valid_recent_plays[:10]]
            speed_skills = [self.calculate_skill_components(p)[1] for p in valid_recent_plays[:10]]
            if aim_skills and speed_skills:
                avg_aim = sum(aim_skills) / len(aim_skills)
                avg_speed = sum(speed_skills) / len(speed_skills)
                ratio = avg_speed / avg_aim if avg_aim else 0
                if ratio > 1.2:
                    insights.append("Your speed outpaces your aim — consider working on precision.")
                elif ratio < 0.8:
                    insights.append("Your aim is stronger than your speed — speed training might help balance.")

        # --- Insight 7: SR consistency vs variety ---
        sr_values = [p.get('beatmap_full', {}).get('difficulty_rating', 0) for p in valid_recent_plays]
        if len(sr_values) >= 6:
            sr_std = statistics.stdev(sr_values)
            if sr_std < 0.3:
                insights.append("You're focusing on a narrow difficulty range — try mixing up challenge levels.")
            elif sr_std > 1.0:
                insights.append("Great variety in map difficulty — good for balanced improvement.")

        # --- Insight 8: High accuracy on easy maps ---
        if len(valid_recent_plays) >= 5:
            easy_high_acc = [
                p for p in valid_recent_plays
                if p.get('accuracy', 0) >= 0.96 and p.get('beatmap_full', {}).get('difficulty_rating', 0) < 3.5
            ]
            if len(easy_high_acc) >= 5:
                insights.append("You’re achieving high accuracy on easier maps — try challenging yourself more.")

        return insights


    def analyze_user_skill(self, user_data: Dict) -> Dict:
        """Perform comprehensive skill analysis"""
        recent_plays = user_data.get('recent_plays', [])
        top_plays = user_data.get('top_plays', [])

        # Filter once, reuse everywhere
        valid_recent_plays = self.filter_valid_plays(recent_plays)
        valid_top_plays = self.filter_valid_plays(top_plays)

        # Skill metrics
        recent_skill = self.calculate_recent_skill(valid_recent_plays)
        peak_skill = self.calculate_peak_skill(valid_top_plays)
        skill_match = self.calculate_skill_match(recent_skill, peak_skill, len(valid_recent_plays))

        # Confidence
        confidence_factors = self.calculate_confidence_factors(recent_plays)
        confidence = self.calculate_confidence_score(confidence_factors)

        # Verdict
        verdict = self.determine_verdict(skill_match, confidence, valid_recent_plays, valid_top_plays)

        # Insights
        insights = self.generate_insights(valid_recent_plays, valid_top_plays)

        return {
            'recent_skill': round(recent_skill, 1),
            'peak_skill': round(peak_skill, 1),
            'skill_match': round(skill_match, 1),
            'confidence': round(confidence, 1),
            'confidence_factors': {
                k: round(v, 3) for k, v in confidence_factors.items()
            },
            'verdict': verdict,
            'insights': insights,
            'data_quality': {
                'valid_recent_plays': len(valid_recent_plays),
                'valid_top_plays': len(valid_top_plays),
                'total_recent_plays': len(recent_plays),
                'total_top_plays': len(top_plays)
            }
        }