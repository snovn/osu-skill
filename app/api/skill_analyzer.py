import math
import statistics
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import pytz

logger = logging.getLogger(__name__)

class SkillAnalyzer:
    def __init__(self, config: Optional[Dict] = None):
        self.config = {
            'old_top_plays_months': 9,
            'old_top_plays_ratio': 0.7,
            'star_rating_gap_threshold': 0.8,
            'accuracy_consistency_threshold': 5.0,
            'high_retry_rate': 0.4,
            'low_retry_rate': 0.15,
            'max_mod_variety': 4,
            'easy_map_threshold': 3.5,
            'high_accuracy_threshold': 0.96,
            'easy_high_acc_min_count': 5,
            'min_recent_plays': 6,
            'min_top_plays': 8,
            'min_confidence_threshold': 20,
            'retry_penalty': 0.95,  # Reduced from 0.85
            'normal_bpm': 180,
            'max_bpm_multiplier': 2.5
        }
        
        if config:
            self.config.update(config)
        
        # Simplified mod multipliers based on actual pp calculations
        self.mod_multipliers = {
            'HD': 1.06,
            'HR': 1.12,
            'DT': 1.18,
            'NC': 1.18,
            'EZ': 0.88,
            'FL': 1.15,
            'HT': 0.82,
            'SO': 0.92,
            'NF': 0.98
        }
        
        # Data-driven skill component weights
        self.skill_weights = {
            'aim': 0.40,
            'speed': 0.35,
            'accuracy': 0.25
        }
        
        # Confidence factor weights
        self.confidence_weights = {
            'volume': 0.35,
            'diversity': 0.25,
            'recency': 0.25,
            'consistency': 0.15
        }

    def validate_play_data(self, play: Dict) -> bool:
        """Validate that a play has the required data for analysis"""
        try:
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
            
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Play validation failed: {e}")
            return False

    def filter_valid_plays(self, plays: List[Dict]) -> List[Dict]:
        """Filter plays to only include those with valid data"""
        return [play for play in plays if self.validate_play_data(play)]

    def calculate_skill_components(self, play: Dict) -> Tuple[float, float, float]:
        """Calculate aim, speed, and accuracy skill components with data-driven scaling"""
        beatmap = play.get('beatmap_full', {})
        accuracy = play.get('accuracy', 0) * 100
        star_rating = beatmap.get('difficulty_rating', 0)
        ar = beatmap.get('ar', 9)
        bpm = beatmap.get('bpm', 120)
        passed = play.get('passed', True)
        
        # Improved accuracy scaling based on pp curve
        if accuracy >= 98:
            acc_factor = 0.98 + (accuracy - 98) * 0.015
        elif accuracy >= 95:
            acc_factor = 0.92 + (accuracy - 95) * 0.02
        elif accuracy >= 90:
            acc_factor = 0.82 + (accuracy - 90) * 0.02
        else:
            acc_factor = max(0.5, accuracy / 100)
        
        fail_penalty = 0.9 if not passed else 1.0

        # Data-driven difficulty scaling
        if star_rating <= 2.0:
            difficulty_scale = 0.7 + (star_rating / 2.0) * 0.3
        elif star_rating <= 4.0:
            difficulty_scale = 1.0 + (star_rating - 2.0) * 0.25
        elif star_rating <= 6.0:
            difficulty_scale = 1.5 + (star_rating - 4.0) * 0.2
        else:
            difficulty_scale = 1.9 + (star_rating - 6.0) * 0.1
        
        # Skill calculations with better coefficients
        aim_skill = acc_factor * (star_rating ** 1.1) * (1 + (ar - 9) * 0.04) * difficulty_scale
        
        bpm_factor = min(bpm / self.config['normal_bpm'], self.config['max_bpm_multiplier'])
        speed_skill = acc_factor * bpm_factor * (star_rating ** 0.9) * difficulty_scale
        
        if accuracy > 85:
            accuracy_base = ((accuracy - 85) / 15) ** 1.2
            accuracy_skill = accuracy_base * (1 + star_rating * 0.08)
        else:
            accuracy_skill = 0

        return (aim_skill * fail_penalty, 
                speed_skill * fail_penalty, 
                accuracy_skill * fail_penalty)

    def get_mod_multiplier(self, mods: List[str]) -> float:
        """Simplified mod multiplier calculation"""
        if not mods:
            return 1.0
        
        multiplier = 1.0
        
        # Handle main difficulty mods with combination bonuses
        has_dt = any(mod in mods for mod in ['DT', 'NC'])
        has_hr = 'HR' in mods
        has_hd = 'HD' in mods
        
        if has_dt and has_hr and has_hd:
            multiplier *= 1.32
        elif has_dt and has_hr:
            multiplier *= 1.26
        elif has_dt and has_hd:
            multiplier *= 1.22
        elif has_hr and has_hd:
            multiplier *= 1.16
        else:
            for mod in mods:
                if mod in self.mod_multipliers:
                    multiplier *= self.mod_multipliers[mod]
        
        return min(max(multiplier, 0.7), 2.2)

    def calculate_skill_score(self, play: Dict) -> float:
        """Calculate overall skill score for a play"""
        aim, speed, accuracy = self.calculate_skill_components(play)
        mods = play.get('mods', [])
        mod_multiplier = self.get_mod_multiplier(mods)
        
        base_score = (self.skill_weights['aim'] * aim + 
                     self.skill_weights['speed'] * speed + 
                     self.skill_weights['accuracy'] * accuracy)
        
        return base_score * mod_multiplier

    def calculate_temporal_weight(self, play_date: str) -> float:
        """Calculate temporal weight with proper error handling"""
        try:
            play_datetime = datetime.fromisoformat(play_date.replace('Z', '+00:00'))
            
            if play_datetime.tzinfo is None:
                play_datetime = play_datetime.replace(tzinfo=pytz.UTC)
            
            current_time = datetime.now(pytz.UTC)
            days_old = (current_time - play_datetime).days
            
            if days_old <= 14:
                return 1.0
            elif days_old <= 30:
                return 0.95
            elif days_old <= 60:
                return 0.88
            elif days_old <= 90:
                return 0.78
            elif days_old <= 180:
                return 0.65
            else:
                return max(0.45, math.exp(-0.004 * days_old))
                
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Failed to parse play date {play_date}: {e}")
            return 0.5

    def detect_retries(self, plays: List[Dict]) -> List[Dict]:
        """Detect and mark retry attempts with consistent data handling"""
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
                    
                    for j in range(max(0, i-6), i):
                        prev_play = plays[j]
                        prev_time = prev_play.get('created_at')
                        prev_beatmap_id = prev_play.get('beatmap', {}).get('id')
                        
                        if prev_time and prev_beatmap_id == beatmap_id:
                            prev_datetime = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))
                            time_diff = abs((current_datetime - prev_datetime).total_seconds())
                            
                            if time_diff < 1200:  # 20 minutes
                                play_copy['is_retry'] = True
                                break
                                
                except (ValueError, TypeError, AttributeError) as e:
                    logger.warning(f"Failed to process retry detection: {e}")
                    
            plays_with_retries.append(play_copy)
        
        return plays_with_retries

    def calculate_weighted_average(self, plays: List[Dict]) -> float:
        """Calculate weighted average skill score with consistent data handling"""
        if not plays:
            return 0.0
        
        plays_with_retries = self.detect_retries(plays)
        
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for i, play in enumerate(plays_with_retries):
            skill_score = self.calculate_skill_score(play)
            temporal_weight = self.calculate_temporal_weight(play.get('created_at', ''))
            
            position_weight = 0.97 ** i
            retry_penalty = self.config['retry_penalty'] if play.get('is_retry', False) else 1.0
            
            final_weight = temporal_weight * position_weight * retry_penalty
            total_weighted_score += skill_score * final_weight
            total_weight += final_weight
        
        return total_weighted_score / total_weight if total_weight > 0 else 0.0

    def calculate_recent_skill(self, recent_plays: List[Dict]) -> float:
        """Calculate recent skill level"""
        return self.calculate_weighted_average(recent_plays[:30])

    def calculate_peak_skill(self, top_plays: List[Dict]) -> float:
        """Calculate peak skill level"""
        top_plays_sorted = sorted(top_plays, key=lambda x: x.get('pp', 0), reverse=True)[:25]
        return self.calculate_weighted_average(top_plays_sorted)

    def calculate_skill_match(self, recent_skill: float, peak_skill: float, recent_count: int) -> float:
        """Calculate skill match percentage with data-driven reliability scaling"""
        if peak_skill == 0:
            return 0.0
        
        match = (recent_skill / peak_skill) * 100
        
        if recent_count >= 25:
            reliability = 1.0
        elif recent_count >= 15:
            reliability = 0.95 + (recent_count - 15) * 0.005
        elif recent_count >= 10:
            reliability = 0.88 + (recent_count - 10) * 0.014
        elif recent_count >= 6:
            reliability = 0.75 + (recent_count - 6) * 0.0325
        else:
            reliability = max(0.6, recent_count * 0.12)
        
        return round(match * reliability, 2)

    def calculate_confidence_factors(self, valid_plays: List[Dict]) -> Dict[str, float]:
        """Calculate confidence factors using consistent valid plays data"""
        if not valid_plays:
            return {'volume': 0, 'diversity': 0, 'recency': 0, 'consistency': 0}
        
        play_count = len(valid_plays)
        
        # Volume factor with better scaling
        if play_count >= 25:
            volume = 1.0
        elif play_count >= 15:
            volume = 0.88 + (play_count - 15) * 0.012
        elif play_count >= 10:
            volume = 0.75 + (play_count - 10) * 0.026
        elif play_count >= 6:
            volume = 0.6 + (play_count - 6) * 0.0375
        else:
            volume = max(0.4, play_count * 0.1)
        
        # Diversity factor
        unique_maps = len(set(
            play.get('beatmap', {}).get('id') 
            for play in valid_plays 
            if play.get('beatmap', {}).get('id')
        ))
        
        if unique_maps >= 15:
            diversity = 1.0
        elif unique_maps >= 10:
            diversity = 0.82 + (unique_maps - 10) * 0.036
        elif unique_maps >= 6:
            diversity = 0.65 + (unique_maps - 6) * 0.0425
        else:
            diversity = max(0.45, unique_maps * 0.108)
        
        # Recency factor
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
                recency = 0.82 + (week_count - 4) * 0.09
            elif week_count >= 2:
                recency = 0.65 + (week_count - 2) * 0.085
            else:
                recency = max(0.5, week_count * 0.325)
                
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Failed to calculate recency factor: {e}")
            recency = 0.6
        
        # Consistency factor
        try:
            accuracies = [play.get('accuracy', 0) * 100 for play in valid_plays]
            if len(accuracies) > 1:
                acc_std = statistics.stdev(accuracies)
                consistency = max(0.5, 1 - (acc_std / 22))
            else:
                consistency = 0.8
        except (statistics.StatisticsError, ValueError) as e:
            logger.warning(f"Failed to calculate consistency factor: {e}")
            consistency = 0.7
        
        return {
            'volume': volume,
            'diversity': diversity,
            'recency': recency,
            'consistency': consistency
        }

    def calculate_confidence_score(self, factors: Dict[str, float]) -> float:
        """Calculate overall confidence score"""
        confidence = sum(
            factors.get(factor, 0) * weight 
            for factor, weight in self.confidence_weights.items()
        )

        confidence = min(confidence * 100, 100.0)

        volume = factors.get("volume", 0)
        if volume < 0.4:
            confidence *= 0.8
        elif volume < 0.6:
            confidence *= 0.92

        return round(confidence, 1)

    def determine_verdict(self, skill_match: float, confidence: float,
                        valid_recent_plays: List[Dict], valid_top_plays: List[Dict]) -> str:
        """Determine overall verdict with data-driven thresholds"""
        
        if len(valid_recent_plays) < self.config['min_recent_plays']:
            if len(valid_recent_plays) == 0 and len(valid_top_plays) >= self.config['min_top_plays']:
                return 'inactive'
            return 'insufficient'
        
        if len(valid_top_plays) < self.config['min_top_plays']:
            return 'insufficient'

        if confidence < self.config['min_confidence_threshold']:
            if confidence >= 16 and skill_match >= 55:
                pass
            else:
                return 'insufficient'

        skill_match = round(skill_match, 1)

        if skill_match >= 88:
            return 'accurate'
        elif skill_match >= 78:
            return 'slightly_rusty'
        elif skill_match >= 58:
            return 'rusty'
        elif skill_match >= 38:
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

        # Top play age analysis
        cutoff_date = datetime.now(pytz.UTC) - timedelta(days=self.config['old_top_plays_months'] * 30)
        old_top_plays = sum(
            1 for play in valid_top_plays[:10]
            if 'created_at' in play and datetime.fromisoformat(play['created_at'].replace('Z', '+00:00')) < cutoff_date
        )
        if old_top_plays > (10 * self.config['old_top_plays_ratio']):
            insights.append("Most top plays are quite old - consider setting new personal bests")

        # Star rating gap analysis
        if len(valid_top_plays) >= 5 and len(valid_recent_plays) >= 5:
            avg_top_sr = sum(p.get('beatmap_full', {}).get('difficulty_rating', 0) for p in valid_top_plays[:5]) / 5
            avg_recent_sr = sum(p.get('beatmap_full', {}).get('difficulty_rating', 0) for p in valid_recent_plays[:10]) / 10

            if avg_recent_sr < avg_top_sr * self.config['star_rating_gap_threshold']:
                insights.append("Playing well below your peak difficulty - consider more challenging maps for improvement")
            elif avg_recent_sr > avg_top_sr * 1.1:
                insights.append("You're attempting harder maps than your current top plays")
                
        # Accuracy consistency analysis
        if len(valid_recent_plays) > 6:
            accuracies = [p.get('accuracy', 0) * 100 for p in valid_recent_plays]
            if len(accuracies) > 1:
                try:
                    acc_std = statistics.stdev(accuracies)
                    avg_acc = statistics.mean(accuracies)
                    if acc_std < self.config['accuracy_consistency_threshold']:
                        if avg_acc >= 98:
                            insights.append("Excellent consistency with high accuracy!")
                        elif avg_acc >= 95:
                            insights.append("Great consistency and solid accuracy")
                        elif avg_acc >= 90:
                            insights.append("Good consistency — but aim for higher accuracy")
                        else:
                            insights.append("Stable consistency, but focus on improving overall accuracy")
                except statistics.StatisticsError:
                    pass

        # Retry behavior analysis
        retry_count = sum(1 for play in plays_with_retries if play.get('is_retry', False))
        retry_rate = retry_count / len(plays_with_retries) if plays_with_retries else 0

        if retry_rate > self.config['high_retry_rate']:
            insights.append("High retry rate - shows dedication to peak performance")
        elif retry_rate < self.config['low_retry_rate']:
            insights.append("Low retry rate - good for building consistency")

        # Mod variety analysis
        mod_usage = {}
        for play in valid_recent_plays:
            mods = play.get('mods', [])
            mod_key = '+'.join(sorted(mods)) if mods else 'NM'
            mod_usage[mod_key] = mod_usage.get(mod_key, 0) + 1

        if len(mod_usage) == 1:
            insights.append("Consider trying different mods to develop diverse skills")
        elif len(mod_usage) > self.config['max_mod_variety']:
            insights.append("Good mod variety - you're developing well-rounded skills")

        return insights

    def analyze_user_skill(self, user_data: Dict) -> Dict:
        """Perform comprehensive skill analysis with consistent data handling"""
        recent_plays = user_data.get('recent_plays', [])
        top_plays = user_data.get('top_plays', [])

        valid_recent_plays = self.filter_valid_plays(recent_plays)
        valid_top_plays = self.filter_valid_plays(top_plays)

        recent_skill = self.calculate_recent_skill(valid_recent_plays)
        peak_skill = self.calculate_peak_skill(valid_top_plays)
        skill_match = self.calculate_skill_match(recent_skill, peak_skill, len(valid_recent_plays))

        confidence_factors = self.calculate_confidence_factors(valid_recent_plays)
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