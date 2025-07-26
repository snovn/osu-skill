import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import hashlib

class OsuClient:
    def __init__(self):
        self.client_id = os.getenv('OSU_CLIENT_ID')
        self.client_secret = os.getenv('OSU_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            raise ValueError("OSU_CLIENT_ID and OSU_CLIENT_SECRET environment variables must be set")
        
        self.access_token = None
        self.token_expires_at = None
        self.base_url = 'https://osu.ppy.sh/api/v2'
        self.session = requests.Session()
        
        # Enhanced caching
        self.beatmap_cache = {}
        self.user_cache = {}
        self.score_cache = {}
        self.cache_lock = threading.Lock()
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.05  # 50ms between requests (more aggressive)
        
        # Performance optimization
        self.session.headers.update({
            'User-Agent': 'osu-skillcheck/1.0',
            'Connection': 'keep-alive'
        })
        
    def get_client_credentials_token(self) -> bool:
        """Get client credentials token for API access"""
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return True
            
        try:
            response = self.session.post('https://osu.ppy.sh/oauth/token', json={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials',
                'scope': 'public'
            })
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get('access_token')
                expires_in = data.get('expires_in', 86400)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                
                # Update session headers
                self.session.headers.update({'Authorization': f'Bearer {self.access_token}'})
                return True
            else:
                print(f"Token request failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Token request error: {e}")
            return False
    
    def _rate_limit(self):
        """Enforce rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _get_cache_key(self, endpoint: str, params: Dict = None) -> str:
        """Generate cache key for request"""
        cache_string = f"{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.md5(cache_string.encode()).hexdigest()
    
    def make_request(self, endpoint: str, params: Dict = None, cache_timeout: int = 300) -> Optional[Dict]:
        """Make authenticated request to osu! API with caching and rate limiting"""
        if not self.get_client_credentials_token():
            print("Failed to get access token")
            return None
        
        # Check cache first
        cache_key = self._get_cache_key(endpoint, params)
        with self.cache_lock:
            if cache_key in self.score_cache:
                cached_data, cached_time = self.score_cache[cache_key]
                if time.time() - cached_time < cache_timeout:
                    return cached_data
        
        self._rate_limit()
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params or {}, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Cache the result
                with self.cache_lock:
                    self.score_cache[cache_key] = (data, time.time())
                
                return data
            elif response.status_code == 429:  # Rate limit
                print("Rate limited, waiting 2 seconds...")
                time.sleep(2)
                return self.make_request(endpoint, params, cache_timeout)
            elif response.status_code == 404:
                print(f"Resource not found: {endpoint}")
                return None
            else:
                print(f"API request failed: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"Request timeout for {endpoint}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
    
    def get_user_info(self, username: str) -> Optional[Dict]:
        """Get user profile information with caching"""
        if not username:
            return None

        # Check user cache first
        with self.cache_lock:
            if username in self.user_cache:
                cached_data, cached_time = self.user_cache[username]
                if time.time() - cached_time < 600:  # 10 minute cache
                    return cached_data

        # If it's all digits, tell API to treat it as a username
        if username.isdigit():
            endpoint = f"users/{username}/osu"
            params = {'key': 'username'}
        else:
            endpoint = f"users/{username}/osu"
            params = None

        user_data = self.make_request(endpoint, params=params, cache_timeout=600)

        if user_data:
            with self.cache_lock:
                self.user_cache[username] = (user_data, time.time())

        return user_data

    
    def get_user_scores(self, user_id: int, score_type: str = 'best', limit: int = 50) -> List[Dict]:
        """Get user scores (best/recent) with caching"""
        if not user_id:
            return []
        
        params = {'limit': limit, 'mode': 'osu'}
        data = self.make_request(f"users/{user_id}/scores/{score_type}", params, cache_timeout=180)
        return data or []
    
    def get_beatmap_info(self, beatmap_id: int) -> Optional[Dict]:
        """Get beatmap information with aggressive caching"""
        if not beatmap_id:
            return None
            
        # Check cache first
        with self.cache_lock:
            if beatmap_id in self.beatmap_cache:
                return self.beatmap_cache[beatmap_id]
        
        # Fetch from API
        beatmap_data = self.make_request(f"beatmaps/{beatmap_id}", cache_timeout=3600)  # 1 hour cache
        
        # Cache the result
        if beatmap_data:
            with self.cache_lock:
                self.beatmap_cache[beatmap_id] = beatmap_data
        
        return beatmap_data
    
    def get_beatmaps_batch(self, beatmap_ids: List[int], max_workers: int = 10, prefix: str = "") -> Dict[int, Dict]:
        """Get multiple beatmaps concurrently with optimized threading"""
        if not beatmap_ids:
            return {}
        
        # Check cache first
        results = {}
        uncached_ids = []
        
        with self.cache_lock:
            for beatmap_id in beatmap_ids:
                if beatmap_id in self.beatmap_cache:
                    results[beatmap_id] = self.beatmap_cache[beatmap_id]
                else:
                    uncached_ids.append(beatmap_id)
        
        if not uncached_ids:
            return results
        
        # Add prefix to debug output
        debug_prefix = f"[{prefix}] " if prefix else ""
        print(f"{debug_prefix}Fetching {len(uncached_ids)} beatmaps from API...")
        
        # Fetch uncached beatmaps in smaller batches
        batch_size = 20
        for i in range(0, len(uncached_ids), batch_size):
            batch = uncached_ids[i:i + batch_size]
            
            with ThreadPoolExecutor(max_workers=min(max_workers, len(batch))) as executor:
                future_to_id = {
                    executor.submit(self.get_beatmap_info, beatmap_id): beatmap_id 
                    for beatmap_id in batch
                }
                
                for future in as_completed(future_to_id):
                    beatmap_id = future_to_id[future]
                    try:
                        beatmap_data = future.result()
                        if beatmap_data:
                            results[beatmap_id] = beatmap_data
                    except Exception as e:
                        print(f"Error fetching beatmap {beatmap_id}: {e}")
        
        return results
    
    def get_user_recent_activity(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get recent plays with optimized filtering"""
        recent_scores = self.get_user_scores(user_id, 'recent', limit)
        
        if not recent_scores:
            return []
        
        # Filter by last 60 days
        sixty_days_ago = datetime.now() - timedelta(days=60)
        filtered_scores = []
        
        for score in recent_scores:
            # Check for valid date
            if not score.get('created_at'):
                continue

            # Check if the beatmap is ranked or loved
            beatmap = score.get('beatmap')
            if not beatmap:
                continue
            status = beatmap.get('status')
            if status not in ('ranked', 'loved', 'qualified'):
                continue

            try:
                play_date = datetime.fromisoformat(score['created_at'].replace('Z', '+00:00'))
                if play_date.replace(tzinfo=None) >= sixty_days_ago:
                    filtered_scores.append(score)
            except ValueError:
                continue

        
        return filtered_scores
    
    def detect_retries(self, scores: List[Dict]) -> List[Dict]:
        """Detect and mark retry attempts (same map < 30 mins apart)"""
        if not scores:
            return []
        
        # Sort by timestamp (newest first)
        sorted_scores = sorted(scores, key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Track seen beatmaps with their timestamps
        beatmap_timestamps = {}
        
        for score in sorted_scores:
            beatmap_id = score.get('beatmap', {}).get('id')
            timestamp_str = score.get('created_at')
            
            if not beatmap_id or not timestamp_str:
                score['is_retry'] = False
                continue
                
            try:
                current_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                if beatmap_id in beatmap_timestamps:
                    # Check if this play is within 30 minutes of previous play on same map
                    prev_time = beatmap_timestamps[beatmap_id]
                    time_diff = abs((current_time - prev_time).total_seconds())
                    
                    if time_diff < 1800:  # 30 minutes = 1800 seconds
                        score['is_retry'] = True
                    else:
                        score['is_retry'] = False
                        beatmap_timestamps[beatmap_id] = current_time
                else:
                    score['is_retry'] = False
                    beatmap_timestamps[beatmap_id] = current_time
                    
            except ValueError:
                score['is_retry'] = False
        
        return sorted_scores
    
    def calculate_basic_skill_score(self, score: Dict) -> float:
        """Calculate basic skill score for quality filtering"""
        if not score.get('beatmap_full'):
            return 0.0
            
        accuracy = score.get('accuracy', 0) * 100  # Convert to percentage
        star_rating = score.get('beatmap_full', {}).get('difficulty_rating', 0)
        ar = score.get('beatmap_full', {}).get('ar', 0)
        bpm = score.get('beatmap_full', {}).get('bpm', 0)
        
        # Basic skill components (simplified version)
        aim_skill = accuracy * (star_rating ** 0.5)
        speed_skill = accuracy * (bpm / 100)
        accuracy_skill = accuracy * ar
        
        # Weighted combination
        skill_score = (0.4 * aim_skill + 0.3 * speed_skill + 0.3 * accuracy_skill)
        
        # Apply retry penalty
        if score.get('is_retry', False):
            skill_score *= 0.7
        
        return skill_score
    
    def filter_recent_for_analysis(self, recent_plays: List[Dict], target_count: int = 25) -> List[Dict]:
        """Filter recent plays for analysis with quality-based selection"""
        if not recent_plays:
            return []
        
        # First detect retries
        plays_with_retries = self.detect_retries(recent_plays)
        
        # Calculate skill scores for each play
        for play in plays_with_retries:
            play['skill_score'] = self.calculate_basic_skill_score(play)
        
        # Sort by skill score (highest first) to get best plays
        quality_sorted = sorted(plays_with_retries, key=lambda x: x.get('skill_score', 0), reverse=True)
        
        # Take the best plays up to target count
        # If player has fewer plays, take what they have
        selected_plays = quality_sorted[:min(target_count, len(quality_sorted))]
        
        # If we have very few plays, don't filter too aggressively
        if len(selected_plays) < 10 and len(quality_sorted) >= 10:
            selected_plays = quality_sorted[:10]
        
        return selected_plays
    
    def enrich_scores_with_beatmap_data(self, scores: List[Dict], prefix: str = "") -> List[Dict]:
        """Add beatmap information to scores using optimized batch processing"""
        if not scores:
            return []
        
        # Extract unique beatmap IDs
        beatmap_ids = list(set(
            score.get('beatmap', {}).get('id') 
            for score in scores 
            if score.get('beatmap', {}).get('id')
        ))
        
        if not beatmap_ids:
            return scores
        
        # Get beatmap data in batch with prefix for debugging
        beatmap_data = self.get_beatmaps_batch(beatmap_ids, prefix=prefix)
        
        # Enrich scores
        enriched_scores = []
        for score in scores:
            beatmap_id = score.get('beatmap', {}).get('id')
            if beatmap_id and beatmap_id in beatmap_data:
                score['beatmap_full'] = beatmap_data[beatmap_id]
            enriched_scores.append(score)
        
        return enriched_scores
    
    def get_comprehensive_user_data(self, username: str, score_limit: int = 25) -> Dict:
        """Get all user data needed for skill analysis with fair score limiting"""
        if not username:
            return {}
        
        print(f"Fetching user info for {username}...")
        start_time = time.time()
        
        user_info = self.get_user_info(username)
        if not user_info:
            return {}
        
        user_id = user_info.get('id')
        if not user_id:
            return {}
        
        print(f"User info fetched in {time.time() - start_time:.2f}s")
        
        # Get scores concurrently with better limits
        scores_start = time.time()
        
        def get_top_plays():
            # Get more than we need to allow for filtering
            return self.get_user_scores(user_id, 'best', score_limit + 10)
        
        def get_recent_plays():
            # Get more than we need to allow for filtering
            return self.get_user_recent_activity(user_id, score_limit + 10)
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            top_future = executor.submit(get_top_plays)
            recent_future = executor.submit(get_recent_plays)
            
            top_plays_raw = top_future.result()
            recent_plays_raw = recent_future.result()
        
        # Apply quality filtering and retry detection to recent plays
        recent_plays_filtered = self.filter_recent_for_analysis(recent_plays_raw, score_limit)
        
        # For top plays, just limit and detect retries (they're already sorted by pp)
        top_plays_limited = top_plays_raw[:score_limit] if top_plays_raw else []
        top_plays = self.detect_retries(top_plays_limited)
        
        print(f"Scores processed: {len(top_plays)} top plays, {len(recent_plays_filtered)} recent plays")
        print(f"Quality filtering: {len(recent_plays_raw)} → {len(recent_plays_filtered)} recent plays")
        
        print(f"Scores fetched in {time.time() - scores_start:.2f}s")
        # print(f"Limited to    {len(top_plays)} top plays and {len(get_recent_plays)} recent plays")
        
        # Enrich with beatmap data
        enrich_start = time.time()
        
        def enrich_top():
            return self.enrich_scores_with_beatmap_data(top_plays, prefix="TOP")
        
        def enrich_recent():
            return self.enrich_scores_with_beatmap_data(recent_plays_filtered, prefix="RECENT")
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            top_future = executor.submit(enrich_top)
            recent_future = executor.submit(enrich_recent)
            
            top_plays_enriched = top_future.result()
            recent_plays_enriched = recent_future.result()
        
        print(f"Enrichment completed in {time.time() - enrich_start:.2f}s")
        print(f"Total data fetch time: {time.time() - start_time:.2f}s")
        
        return {
            'user_info': user_info,
            'top_plays': top_plays_enriched,
            'recent_plays': recent_plays_enriched
        }
    
    def clear_cache(self):
        """Clear all caches"""
        with self.cache_lock:
            self.beatmap_cache.clear()
            self.user_cache.clear()
            self.score_cache.clear()
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        with self.cache_lock:
            return {
                'cached_beatmaps': len(self.beatmap_cache),
                'cached_users': len(self.user_cache),
                'cached_scores': len(self.score_cache),
                'cache_size_mb': (
                    len(json.dumps(self.beatmap_cache)) + 
                    len(json.dumps(self.user_cache)) + 
                    len(json.dumps(self.score_cache))
                ) / (1024 * 1024)
            }
    
    def preload_user_data(self, username: str) -> bool:
        """Preload user data in background"""
        try:
            threading.Thread(
                target=self.get_comprehensive_user_data,
                args=(username,),
                daemon=True
            ).start()
            return True
        except Exception as e:
            print(f"Error preloading data for {username}: {e}")
            return False