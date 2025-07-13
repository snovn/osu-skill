import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import time
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
import logging

class ImprovedOsuClient:
    def __init__(self):
        self.client_id = os.getenv('OSU_CLIENT_ID')
        self.client_secret = os.getenv('OSU_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            raise ValueError("OSU_CLIENT_ID and OSU_CLIENT_SECRET environment variables must be set")
        
        self.access_token = None
        self.token_expires_at = None
        self.base_url = 'https://osu.ppy.sh/api/v2'
        self.session = requests.Session()
        
        # Cache for beatmap data to avoid repeated API calls
        self.beatmap_cache = {}
        self.cache_expires = {}
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def get_client_credentials_token(self) -> bool:
        """Get client credentials token with better error handling"""
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return True
            
        try:
            response = self.session.post('https://osu.ppy.sh/oauth/token', json={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials',
                'scope': 'public'
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get('access_token')
                expires_in = data.get('expires_in', 86400)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                self.logger.info("Successfully obtained access token")
                return True
            else:
                self.logger.error(f"Token request failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Token request error: {e}")
            return False
    
    def rate_limit(self):
        """Simple rate limiting to avoid API limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
    
    def make_request(self, endpoint: str, params: Dict = None, retries: int = 3) -> Optional[Dict]:
        """Make authenticated request with better error handling and retries"""
        if not self.get_client_credentials_token():
            self.logger.error("Failed to get access token")
            return None
        
        self.rate_limit()
        
        headers = {'Authorization': f'Bearer {self.access_token}'}
        url = f"{self.base_url}/{endpoint}"
        
        for attempt in range(retries):
            try:
                response = self.session.get(url, headers=headers, params=params or {}, timeout=10)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:  # Rate limit
                    wait_time = min(5 * (2 ** attempt), 30)  # Exponential backoff
                    self.logger.warning(f"Rate limited, waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                elif response.status_code == 404:
                    self.logger.warning(f"Resource not found: {endpoint}")
                    return None
                else:
                    self.logger.error(f"API request failed: {response.status_code} - {response.text}")
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    return None
                    
            except requests.exceptions.Timeout:
                self.logger.error(f"Request timeout for {endpoint}")
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return None
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Request error: {e}")
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return None
        
        return None
    
    def get_user_info(self, username: str) -> Optional[Dict]:
        """Get user profile information"""
        if not username:
            return None
        
        self.logger.info(f"Fetching user info for: {username}")
        return self.make_request(f"users/{username}/osu")
    
    def get_user_scores_batch(self, user_id: int, score_type: str = 'best', limit: int = 100) -> List[Dict]:
        """Get user scores in larger batches"""
        if not user_id:
            return []
        
        self.logger.info(f"Fetching {score_type} scores for user {user_id}")
        params = {'limit': min(limit, 100), 'mode': 'osu'}  # API limit is 100
        data = self.make_request(f"users/{user_id}/scores/{score_type}", params)
        return data or []
    
    def get_beatmap_info_cached(self, beatmap_id: int) -> Optional[Dict]:
        """Get beatmap information with caching"""
        if not beatmap_id:
            return None
        
        # Check cache
        if beatmap_id in self.beatmap_cache:
            if datetime.now() < self.cache_expires.get(beatmap_id, datetime.now()):
                return self.beatmap_cache[beatmap_id]
        
        # Fetch from API
        beatmap_info = self.make_request(f"beatmaps/{beatmap_id}")
        
        if beatmap_info:
            # Cache for 1 hour
            self.beatmap_cache[beatmap_id] = beatmap_info
            self.cache_expires[beatmap_id] = datetime.now() + timedelta(hours=1)
        
        return beatmap_info
    
    def get_beatmaps_batch(self, beatmap_ids: List[int]) -> Dict[int, Dict]:
        """Get multiple beatmaps efficiently"""
        if not beatmap_ids:
            return {}
        
        results = {}
        uncached_ids = []
        
        # Check cache first
        for beatmap_id in beatmap_ids:
            if beatmap_id in self.beatmap_cache:
                if datetime.now() < self.cache_expires.get(beatmap_id, datetime.now()):
                    results[beatmap_id] = self.beatmap_cache[beatmap_id]
                    continue
            uncached_ids.append(beatmap_id)
        
        # Fetch uncached beatmaps
        # Note: osu! API doesn't have a batch endpoint for beatmaps, so we need to make individual requests
        # But we can use threading to speed this up
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_id = {
                executor.submit(self.get_beatmap_info_cached, beatmap_id): beatmap_id 
                for beatmap_id in uncached_ids
            }
            
            for future in future_to_id:
                beatmap_id = future_to_id[future]
                try:
                    beatmap_info = future.result()
                    if beatmap_info:
                        results[beatmap_id] = beatmap_info
                except Exception as e:
                    self.logger.error(f"Error fetching beatmap {beatmap_id}: {e}")
        
        return results
    
    def get_user_recent_activity_optimized(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get recent plays with better filtering"""
        self.logger.info(f"Fetching recent activity for user {user_id}")
        
        # Get more recent scores to ensure we have enough data
        recent_scores = self.get_user_scores_batch(user_id, 'recent', min(limit * 2, 100))
        
        if not recent_scores:
            self.logger.warning(f"No recent scores found for user {user_id}")
            return []
        
        # Filter by last 60 days
        sixty_days_ago = datetime.now() - timedelta(days=60)
        filtered_scores = []
        
        for score in recent_scores:
            if score.get('created_at'):
                try:
                    play_date = datetime.fromisoformat(score['created_at'].replace('Z', '+00:00'))
                    if play_date.replace(tzinfo=None) >= sixty_days_ago:
                        filtered_scores.append(score)
                except ValueError:
                    continue
        
        self.logger.info(f"Found {len(filtered_scores)} recent plays within 60 days")
        return filtered_scores[:limit]
    
    def enrich_scores_with_beatmap_data_optimized(self, scores: List[Dict]) -> List[Dict]:
        """Add beatmap information to scores efficiently"""
        if not scores:
            return []
        
        self.logger.info(f"Enriching {len(scores)} scores with beatmap data")
        
        # Extract all unique beatmap IDs
        beatmap_ids = list(set(
            score.get('beatmap', {}).get('id') 
            for score in scores 
            if score.get('beatmap', {}).get('id')
        ))
        
        if not beatmap_ids:
            self.logger.warning("No beatmap IDs found in scores")
            return scores
        
        # Get all beatmaps in batch
        beatmaps = self.get_beatmaps_batch(beatmap_ids)
        
        # Enrich scores
        enriched_scores = []
        for score in scores:
            beatmap_id = score.get('beatmap', {}).get('id')
            if beatmap_id and beatmap_id in beatmaps:
                score['beatmap_full'] = beatmaps[beatmap_id]
                enriched_scores.append(score)
            else:
                # Include score even if beatmap info is missing
                enriched_scores.append(score)
        
        self.logger.info(f"Successfully enriched {len(enriched_scores)} scores")
        return enriched_scores
    
    def get_comprehensive_user_data_optimized(self, username: str) -> Dict:
        """Get all user data with optimized API calls"""
        if not username:
            return {}
        
        self.logger.info(f"Starting comprehensive analysis for user: {username}")
        start_time = time.time()
        
        # Get user info
        user_info = self.get_user_info(username)
        if not user_info:
            self.logger.error(f"Could not fetch user info for {username}")
            return {}
        
        user_id = user_info.get('id')
        if not user_id:
            self.logger.error(f"No user ID found for {username}")
            return {}
        
        self.logger.info(f"Found user {username} with ID {user_id}")
        
        # Get scores in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            top_plays_future = executor.submit(self.get_user_scores_batch, user_id, 'best', 50)
            recent_plays_future = executor.submit(self.get_user_recent_activity_optimized, user_id, 50)
            
            top_plays = top_plays_future.result()
            recent_plays = recent_plays_future.result()
        
        self.logger.info(f"Fetched {len(top_plays)} top plays and {len(recent_plays)} recent plays")
        
        # Enrich with beatmap data
        all_scores = top_plays + recent_plays
        enriched_scores = self.enrich_scores_with_beatmap_data_optimized(all_scores)
        
        # Split back into top and recent
        top_plays_enriched = enriched_scores[:len(top_plays)]
        recent_plays_enriched = enriched_scores[len(top_plays):]
        
        end_time = time.time()
        self.logger.info(f"Comprehensive data fetch completed in {end_time - start_time:.2f} seconds")
        
        return {
            'user_info': user_info,
            'top_plays': top_plays_enriched,
            'recent_plays': recent_plays_enriched,
            'fetch_time': end_time - start_time
        }
    
    def get_user_replay_data(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Get recent plays with replay data (if available)"""
        # Note: This would require additional API endpoints or replay file parsing
        # For now, we'll simulate enhanced play data
        recent_plays = self.get_user_scores_batch(user_id, 'recent', limit)
        
        enhanced_plays = []
        for play in recent_plays:
            # Add simulated replay-derived metrics
            # In a real implementation, you'd parse actual replay files
            enhanced_play = play.copy()
            enhanced_play['replay_metrics'] = {
                'unstable_rate': play.get('statistics', {}).get('count_100', 0) * 2 + 
                               play.get('statistics', {}).get('count_50', 0) * 5,
                'avg_hit_error': None,  # Would need replay parsing
                'completion_rate': 1.0 if play.get('rank', 'F') != 'F' else 0.8
            }
            enhanced_plays.append(enhanced_play)
        
        return enhanced_plays
    
    def __del__(self):
        """Clean up session on destruction"""
        if hasattr(self, 'session'):
            self.session.close()