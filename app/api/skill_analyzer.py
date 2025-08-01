import math
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import pytz

class SkillAnalyzer:
    def __init__(self):
        self.mod_multipliers = {
            'HD': 1.06, 'HR': 1.12, 'DT': 1.18, 'EZ': 0.88, 'FL': 1.15,
            'SO': 0.92, 'NF': 0.98, 'SD': 1.0, 'PF': 1.0, 'NC': 1.18, 'HT': 0.82
        }
        
        self.min_recent_plays = 6
        self.min_top_plays = 8
        self.min_confidence_threshold = 20
        
        self.THRESHOLDS = {
            'old_top_plays_months': 9,
            'old_top_plays_ratio': 0.7,
            'star_rating_gap_low': 0.7,
            'star_rating_gap_high': 1.15,
            'accuracy_consistency_threshold': 5.0,
            'high_retry_rate': 0.4,
            'low_retry_rate': 0.15,
            'max_mod_variety': 4,
            'sr_consistency_low': 0.3,
            'sr_consistency_high': 1.0,
            'easy_map_threshold': 3.5,
            'high_accuracy_threshold': 0.96,
            'easy_high_acc_min_count': 5,
            'normal_bpm': 180,
            'max_bpm_multiplier': 2.5
        }

    def get_effective_star_rating(self, play: Dict) -> float:
        """Calculate effective star rating accounting for mods"""
        base_sr = play.get('beatmap_full', {}).get('difficulty_rating', 0)
        mods = play.get('mods', [])
        
        if not mods:
            return base_sr
        
        # DT/NC increases star rating significantly
        if 'DT' in mods or 'NC' in mods:
            base_sr *= 1.4  # Approximate DT star rating multiplier
        
        # HT decreases star rating
        if 'HT' in mods:
            base_sr *= 0.75  # Approximate HT star rating multiplier
            
        # HR increases star rating moderately
        if 'HR' in mods:
            base_sr *= 1.1  # Approximate HR star rating multiplier
            
        # EZ decreases star rating
        if 'EZ' in mods:
            base_sr *= 0.5  # Approximate EZ star rating multiplier
        
        return base_sr

    def validate_play_data(self, play: Dict) -> bool:
        """Validate that a play has the required data for analysis"""
        required_fields = ['accuracy', 'created_at']
        
        for field in required_fields:
            if not play.get(field):
                return False
        
        beatmap_full = play.get('beatmap_full', {})
        if not beatmap_full:
            return False
            
        beatmap_fields = ['difficulty_rating', 'ar', 'bpm']
        for field in beatmap_fields:
            if beatmap_full.get(field) is None:
                return False
        
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
        
        mods = play.get('mods', [])
        if any(mod in mods for mod in ['RX', 'AP']):
            return False
        
        return True

    def filter_valid_plays(self, plays: List[Dict]) -> List[Dict]:
        """Filter plays to only include those with valid data"""
        return [play for play in plays if self.validate_play_data(play)]

    def calculate_skill_components(self, play: Dict) -> Tuple[float, float, float]:
        """Calculate aim, speed, and accuracy skill components"""
        beatmap = play.get('beatmap_full', {})
        accuracy = play.get('accuracy', 0) * 100
        star_rating = beatmap.get('difficulty_rating', 0)
        ar = beatmap.get('ar', 9)
        bpm = beatmap.get('bpm', 120)
        passed = play.get('passed', True)
        
        # More realistic accuracy scaling
        if accuracy >= 99:
            acc_factor = 0.99 + (accuracy - 99) * 0.01
        elif accuracy >= 96:
            acc_factor = 0.96 + (accuracy - 96) * 0.01
        elif accuracy >= 90:
            acc_factor = 0.90 + (accuracy - 90) * 0.01
        elif accuracy >= 80:
            acc_factor = 0.80 + (accuracy - 80) * 0.01
        else:
            acc_factor = accuracy / 100 * 0.8
        
        fail_penalty = 0.75 if not passed else 1.0

        # More conservative difficulty scaling
        if star_rating <= 3.0:
            difficulty_scale = 0.7 + (star_rating / 3.0) * 0.3
        elif star_rating <= 5.0:
            difficulty_scale = 1.0 + (star_rating - 3.0) * 0.15
        elif star_rating <= 7.0:
            difficulty_scale = 1.3 + (star_rating - 5.0) * 0.2
        else:
            difficulty_scale = 1.7 + (star_rating - 7.0) * 0.1
        
        aim_skill = acc_factor * (star_rating ** 1.1) * (1 + (ar - 9) * 0.03) * difficulty_scale
        
        bpm_factor = min(bpm / self.THRESHOLDS['normal_bpm'], self.THRESHOLDS['max_bpm_multiplier'])
        speed_skill = acc_factor * bpm_factor * (star_rating ** 0.9) * difficulty_scale
        
        # Fixed accuracy skill calculation
        if accuracy >= 95:
            accuracy_base = ((accuracy - 80) / 20) ** 1.2
            accuracy_skill = accuracy_base * (1 + star_rating * 0.08)
        else:
            accuracy_skill = max(0, (accuracy - 60) / 40) * (1 + star_rating * 0.05)

        return aim_skill * fail_penalty, speed_skill * fail_penalty, accuracy_skill * fail_penalty

    def get_mod_multiplier(self, mods: List[str]) -> float:
        """Calculate mod multiplier for a play"""
        if not mods:
            return 1.0
            
        has_dt = 'DT' in mods or 'NC' in mods
        has_hr = 'HR' in mods
        has_hd = 'HD' in mods
        has_ez = 'EZ' in mods
        has_fl = 'FL' in mods
        has_ht = 'HT' in mods
        
        multiplier = 1.0
        
        # Fixed mod combination bonuses
        if has_dt and has_hr and has_hd:
            multiplier *= 1.32
        elif has_dt and has_hr:
            multiplier *= 1.25
        elif has_dt and has_hd:
            multiplier *= 1.22
        elif has_hr and has_hd:
            multiplier *= 1.16
        else:
            if has_dt:
                multiplier *= self.mod_multipliers['DT']
            if has_hr:
                multiplier *= self.mod_multipliers['HR']
            if has_hd:
                multiplier *= self.mod_multipliers['HD']
        
        if has_ez:
            multiplier *= self.mod_multipliers['EZ']
        if has_fl:
            multiplier *= self.mod_multipliers['FL']
        if has_ht:
            multiplier *= self.mod_multipliers['HT']
        
        for mod in mods:
            if mod in ['SO', 'NF', 'SD', 'PF'] and mod in self.mod_multipliers:
                multiplier *= self.mod_multipliers[mod]
        
        return min(max(multiplier, 0.6), 2.2)

    def calculate_skill_score(self, play: Dict) -> float:
        """Calculate overall skill score for a play"""
        aim, speed, accuracy = self.calculate_skill_components(play)
        mods = play.get('mods', [])
        mod_multiplier = self.get_mod_multiplier(mods)
        
        # Rebalanced weights
        base_score = (0.4 * aim + 0.4 * speed + 0.2 * accuracy)
        return base_score * mod_multiplier

    def calculate_temporal_weight(self, play_date: str) -> float:
        """Calculate temporal weight with better error handling"""
        try:
            play_datetime = datetime.fromisoformat(play_date.replace('Z', '+00:00'))
            
            if play_datetime.tzinfo is None:
                play_datetime = play_datetime.replace(tzinfo=pytz.UTC)
            
            current_time = datetime.now(pytz.UTC)
            days_old = (current_time - play_datetime).days
            
            # More gradual decay
            if days_old <= 7:
                return 1.0
            elif days_old <= 14:
                return 0.98
            elif days_old <= 30:
                return 0.93
            elif days_old <= 60:
                return 0.85
            elif days_old <= 90:
                return 0.75
            elif days_old <= 180:
                return 0.6
            else:
                return max(0.35, math.exp(-0.004 * days_old))
        except (ValueError, TypeError, AttributeError):
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
                    
                    for j in range(max(0, i-8), i):
                        prev_play = plays[j]
                        prev_time = prev_play.get('created_at')
                        prev_beatmap_id = prev_play.get('beatmap', {}).get('id')
                        
                        if prev_time and prev_beatmap_id == beatmap_id:
                            prev_datetime = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))
                            time_diff = abs((current_datetime - prev_datetime).total_seconds())
                            
                            if time_diff < 1800:  # Increased to 30 minutes
                                play_copy['is_retry'] = True
                                break
                except (ValueError, TypeError, AttributeError):
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
            
            position_weight = 0.95 ** i  # Less aggressive decay
            retry_penalty = 0.9 if play.get('is_retry', False) else 1.0  # Less harsh penalty
            
            final_weight = temporal_weight * position_weight * retry_penalty
            total_weighted_score += skill_score * final_weight
            total_weight += final_weight
        
        return total_weighted_score / total_weight if total_weight > 0 else 0.0

    def calculate_recent_skill(self, recent_plays: List[Dict]) -> float:
        """Calculate recent skill level"""
        if not recent_plays:
            return 0.0
        
        return self.calculate_weighted_average(recent_plays[:30])

    def calculate_peak_skill(self, top_plays: List[Dict]) -> float:
        """Calculate peak skill level"""
        if not top_plays:
            return 0.0
        
        top_plays_sorted = sorted(top_plays, key=lambda x: x.get('pp', 0), reverse=True)[:25]
        return self.calculate_weighted_average(top_plays_sorted)

    def calculate_skill_match(self, recent_skill: float, peak_skill: float, recent_count: int) -> float:
        """Calculate skill match percentage"""
        if peak_skill == 0:
            return 0.0
        
        match = (recent_skill / peak_skill) * 100
        
        # More generous reliability scaling
        if recent_count >= 20:
            reliability = 1.0
        elif recent_count >= 15:
            reliability = 0.95 + (recent_count - 15) * 0.01
        elif recent_count >= 10:
            reliability = 0.88 + (recent_count - 10) * 0.014
        elif recent_count >= 6:
            reliability = 0.75 + (recent_count - 6) * 0.0325
        else:
            reliability = max(0.6, recent_count * 0.1)
        
        return round(match * reliability, 2)

    def calculate_confidence_factors(self, recent_plays: List[Dict]) -> Dict[str, float]:
        """Calculate confidence factors (without recency)"""
        if not recent_plays:
            return {'volume': 0, 'diversity': 0, 'consistency': 0}
        
        valid_plays = self.filter_valid_plays(recent_plays)
        
        # Volume factor
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
        
        # Diversity factor
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
        
        # Consistency factor
        try:
            accuracies = [play.get('accuracy', 0) * 100 for play in valid_plays]
            if len(accuracies) > 1:
                acc_std = statistics.stdev(accuracies)
                consistency = max(0.3, 1 - (acc_std / 30))  # Less harsh penalty
            else:
                consistency = 0.8
        except (statistics.StatisticsError, ValueError):
            consistency = 0.6
        
        return {
            'volume': volume,
            'diversity': diversity,
            'consistency': consistency
        }

    def calculate_confidence_score(self, factors: Dict[str, float]) -> float:
        """Calculate overall confidence score (adjusted weights without recency)"""
        weights = {
            'volume': 0.40, 
            'diversity': 0.35, 
            'consistency': 0.25 
        }

        confidence = sum(
            factors.get(factor, 0) * weight 
            for factor, weight in weights.items()
        )

        confidence = min(confidence * 100, 100.0)

        volume = factors.get("volume", 0)
        if volume < 0.4:
            confidence *= 0.8  # Less harsh penalty
        elif volume < 0.6:
            confidence *= 0.95

        return round(confidence, 1)

    def determine_verdict(self, skill_match: float, confidence: float,
                        valid_recent_plays: List[Dict], valid_top_plays: List[Dict]) -> str:
        """Determine overall verdict with clearer logic"""
        
        if len(valid_recent_plays) < self.min_recent_plays:
            if len(valid_recent_plays) == 0 and len(valid_top_plays) >= self.min_top_plays:
                return 'inactive'
            return 'insufficient'
        
        if len(valid_top_plays) < self.min_top_plays:
            return 'insufficient'

        if confidence < self.min_confidence_threshold:
            if confidence >= 15 and skill_match >= 50:
                pass
            else:
                return 'insufficient'

        skill_match = round(skill_match, 1)

        if skill_match >= 88:
            return 'accurate'
        elif skill_match >= 78:
            return 'slightly_rusty'
        elif skill_match >= 60:
            return 'rusty'
        elif skill_match >= 40:
            return 'overranked'
        else:
            return 'inactive'

    def generate_insights(self, valid_recent_plays: List[Dict], valid_top_plays: List[Dict]) -> List[str]:
        """Generate insights about the player's performance"""
        insights = []

        if not valid_top_plays or not valid_recent_plays:
            insights.append("Limited data available for comprehensive analysis")
            return insights

        plays_with_retries = self.detect_retries(valid_recent_plays)

        cutoff_date = datetime.now(pytz.UTC) - timedelta(days=self.THRESHOLDS['old_top_plays_months'] * 30)
        old_top_plays = sum(
            1 for play in valid_top_plays[:10]
            if 'created_at' in play and datetime.fromisoformat(play['created_at'].replace('Z', '+00:00')) < cutoff_date
        )
        if old_top_plays > (10 * self.THRESHOLDS['old_top_plays_ratio']):
            insights.append("Most top plays are quite old - consider setting new personal bests")

        # FIXED: Use effective star rating that accounts for mods
        if len(valid_top_plays) >= 5 and len(valid_recent_plays) >= 5:
            avg_top_sr = sum(self.get_effective_star_rating(p) for p in valid_top_plays[:5]) / 5
            avg_recent_sr = sum(self.get_effective_star_rating(p) for p in valid_recent_plays[:10]) / 10

            if avg_recent_sr < avg_top_sr * 0.8:
                insights.append("Playing well below your peak difficulty - consider more challenging maps for improvement")
            elif avg_recent_sr > avg_top_sr * self.THRESHOLDS['star_rating_gap_high']:
                insights.append("You're attempting harder maps than your current top plays")
                
        if len(valid_recent_plays) > 6:
            accuracies = [p.get('accuracy', 0) * 100 for p in valid_recent_plays]
            if len(accuracies) > 1:
                try:
                    acc_std = statistics.stdev(accuracies)
                    avg_acc = statistics.mean(accuracies)
                    if acc_std < self.THRESHOLDS['accuracy_consistency_threshold']:
                        if avg_acc >= 98:
                            insights.append("Excellent consistency with high accuracy!")
                        elif avg_acc >= 95:
                            insights.append("Great consistency and solid accuracy")
                        elif avg_acc >= 90:
                            insights.append("Good consistency — but aim for higher accuracy")
                        elif avg_acc >= 75:
                            insights.append("Stable consistency, but overall performance needs improvement")
                        else:
                            insights.append("Stable consistency, but accuracy is critically low — focus on fundamentals")
                except statistics.StatisticsError:
                    pass

        retry_count = sum(1 for play in plays_with_retries if play.get('is_retry', False))
        retry_rate = retry_count / len(plays_with_retries) if plays_with_retries else 0

        if retry_rate > self.THRESHOLDS['high_retry_rate']:
            insights.append("High retry rate - shows dedication to peak performance")
        elif retry_rate < self.THRESHOLDS['low_retry_rate']:
            insights.append("Low retry rate - good for building consistency")

        mod_usage = {}
        for play in valid_recent_plays:
            mods = play.get('mods', [])
            mod_key = '+'.join(sorted(mods)) if mods else 'NM'
            mod_usage[mod_key] = mod_usage.get(mod_key, 0) + 1

        if len(mod_usage) == 1:
            insights.append("Consider trying different mods to develop diverse skills")
        elif len(mod_usage) > self.THRESHOLDS['max_mod_variety']:
            insights.append("Good mod variety - you're developing well-rounded skills")

            
        return insights

    def analyze_user_skill(self, user_data: Dict) -> Dict:
        """Perform comprehensive skill analysis"""
        recent_plays = user_data.get('recent_plays', [])
        top_plays = user_data.get('top_plays', [])

        valid_recent_plays = self.filter_valid_plays(recent_plays)
        valid_top_plays = self.filter_valid_plays(top_plays)

        recent_skill = self.calculate_recent_skill(valid_recent_plays)
        peak_skill = self.calculate_peak_skill(valid_top_plays)
        skill_match = self.calculate_skill_match(recent_skill, peak_skill, len(valid_recent_plays))

        confidence_factors = self.calculate_confidence_factors(recent_plays)
        confidence = self.calculate_confidence_score(confidence_factors)

        verdict = self.determine_verdict(skill_match, confidence, valid_recent_plays, valid_top_plays)

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