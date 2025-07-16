import os
import json
from datetime import datetime, timedelta  # Add timedelta import here
from typing import Dict, List, Optional
from supabase import create_client, Client
import pytz

class SupabaseDatabase:
    def __init__(self, url: str = None, key: str = None):
        """Initialize Supabase client"""
        self.url = url or os.getenv('SUPABASE_URL')
        self.key = key or os.getenv('SUPABASE_ANON_KEY')
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and key are required. Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables.")
        
        self.client: Client = create_client(self.url, self.key)
        print("Supabase client initialized successfully")
    
    def get_user_by_osu_id(self, osu_id: int) -> Optional[Dict]:
        """Get user by osu ID"""
        try:
            response = self.client.table('users').select('*').eq('osu_id', osu_id).execute()
            
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error getting user by osu_id {osu_id}: {e}")
            return None
    
    def upsert_user(self, user_data: Dict) -> Optional[int]:
        """Insert or update user data with better error handling"""
        try:
            # Validate input
            if not isinstance(user_data, dict):
                raise ValueError(f"Invalid user_data type: {type(user_data)}")
            
            user_id = user_data.get('id')
            if not user_id:
                raise ValueError("Missing user ID in user_data")
            
            # Check if user exists
            existing_user = self.get_user_by_osu_id(user_id)
            
            timestamp = datetime.now(pytz.UTC).isoformat()
            
            # Build user record with safe defaults
            user_record = {
                'osu_id': user_id,
                'username': user_data.get('username', ''),
                'avatar_url': user_data.get('avatar_url', ''),
                'rank': user_data.get('statistics', {}).get('global_rank'),
                'pp': user_data.get('statistics', {}).get('pp'),
                'playcount': user_data.get('statistics', {}).get('play_count'),
                'updated_at': timestamp
            }
            
            # Validate numeric fields
            for field in ['rank', 'pp', 'playcount']:
                if user_record[field] is not None and not isinstance(user_record[field], (int, float)):
                    print(f"Warning: Invalid {field} value: {user_record[field]}, setting to None")
                    user_record[field] = None
            
            if existing_user:
                # Update existing user
                response = self.client.table('users').update(user_record).eq('osu_id', user_id).execute()
                if response.data:
                    print(f"Updated user {user_data.get('username')} (ID: {existing_user['id']})")
                    return existing_user['id']
                else:
                    print(f"Warning: User update returned no data for osu_id: {user_id}")
                    return existing_user['id']  # Return existing ID as fallback
            else:
                # Insert new user
                user_record['created_at'] = timestamp
                response = self.client.table('users').insert(user_record).execute()
                
                if response.data and len(response.data) > 0:
                    new_user_id = response.data[0]['id']
                    print(f"Created new user {user_data.get('username')} (ID: {new_user_id})")
                    return new_user_id
                else:
                    print(f"Error: User creation returned no data for osu_id: {user_id}")
                    return None
                        
        except Exception as e:
            print(f"Error upserting user with osu_id {user_data.get('id', 'unknown')}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_analysis_result(self, user_id: int, analysis_result: Dict) -> Optional[int]:
        """Save analysis result to database with better error handling"""
        try:
            # Validate input
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError(f"Invalid user_id: {user_id}")
            
            if not isinstance(analysis_result, dict):
                raise ValueError(f"Invalid analysis_result type: {type(analysis_result)}")
            
            timestamp = datetime.now(pytz.UTC).isoformat()
            
            # Ensure all required fields have default values
            record = {
                'user_id': user_id,
                'recent_skill': analysis_result.get('recent_skill', 0) or 0,
                'peak_skill': analysis_result.get('peak_skill', 0) or 0,
                'skill_match': analysis_result.get('skill_match', 0) or 0,
                'confidence': analysis_result.get('confidence', 0) or 0,
                'verdict': analysis_result.get('verdict', 'unknown') or 'unknown',
                'insights': json.dumps(analysis_result.get('insights', [])),
                'confidence_factors': json.dumps(analysis_result.get('confidence_factors', {})),
                'created_at': timestamp
            }
            
            # Validate numeric fields
            for field in ['recent_skill', 'peak_skill', 'skill_match', 'confidence']:
                if not isinstance(record[field], (int, float)) or record[field] < 0:
                    print(f"Warning: Invalid {field} value: {record[field]}, setting to 0")
                    record[field] = 0
            
            response = self.client.table('analysis_results').insert(record).execute()
            
            if response.data and len(response.data) > 0:
                analysis_id = response.data[0]['id']
                print(f"Successfully saved analysis result (ID: {analysis_id}) for user_id: {user_id}")
                return analysis_id
            else:
                print(f"No data returned from analysis insert for user_id: {user_id}")
                return None
                
        except Exception as e:
            print(f"Error saving analysis result for user_id {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_latest_analysis(self, user_id: int) -> Optional[Dict]:
        """Get latest analysis result for user with better error handling"""
        try:
            if not isinstance(user_id, int) or user_id <= 0:
                print(f"Invalid user_id provided: {user_id}")
                return None
            
            response = (self.client.table('analysis_results')
                    .select('*')
                    .eq('user_id', user_id)
                    .order('created_at', desc=True)
                    .limit(1)
                    .execute())
            
            if response.data and len(response.data) > 0:
                row = response.data[0]
                
                # Validate the data before processing
                result = {
                    'recent_skill': row.get('recent_skill', 0) or 0,
                    'peak_skill': row.get('peak_skill', 0) or 0,
                    'skill_match': row.get('skill_match', 0) or 0,
                    'confidence': row.get('confidence', 0) or 0,
                    'verdict': row.get('verdict', 'unknown') or 'unknown',
                    'insights': [],
                    'confidence_factors': {},
                    'created_at': row.get('created_at')
                }
                
                # Safely parse JSON fields
                try:
                    if row.get('insights'):
                        result['insights'] = json.loads(row['insights'])
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"Warning: Failed to parse insights JSON: {e}")
                    result['insights'] = []
                
                try:
                    if row.get('confidence_factors'):
                        result['confidence_factors'] = json.loads(row['confidence_factors'])
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"Warning: Failed to parse confidence_factors JSON: {e}")
                    result['confidence_factors'] = {}
                
                print(f"Retrieved cached analysis for user_id {user_id}: {result['created_at']}")
                return result
            else:
                print(f"No cached analysis found for user_id {user_id} (this is normal for new users)")
                return None
                
        except Exception as e:
            print(f"Error getting latest analysis for user_id {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_leaderboard(self, user_id: int, analysis_result: Dict):
        """Update user's leaderboard position with better error handling for new users"""
        try:
            # Validate inputs
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError(f"Invalid user_id: {user_id}")
            
            if not isinstance(analysis_result, dict):
                raise TypeError(f"Expected dict for analysis_result, got {type(analysis_result).__name__}")

            # Calculate skill score with robust default values
            recent_skill = analysis_result.get('recent_skill', 0) or 0
            peak_skill = analysis_result.get('peak_skill', 0) or 0
            skill_match = analysis_result.get('skill_match', 0) or 0
            confidence = analysis_result.get('confidence', 0) or 0
            verdict = analysis_result.get('verdict', 'unknown') or 'unknown'
            
            # Validate numeric fields
            for field_name, value in [('recent_skill', recent_skill), ('peak_skill', peak_skill), 
                                    ('skill_match', skill_match), ('confidence', confidence)]:
                if not isinstance(value, (int, float)) or value < 0:
                    print(f"Warning: Invalid {field_name} value: {value}, setting to 0")
                    locals()[field_name] = 0
            
            # Improved skill score calculation with bounds checking
            normalized_confidence = max(30, min(confidence, 100))
            skill_score = (recent_skill * 0.7 + peak_skill * 0.3) * (normalized_confidence / 100)
            
            # Ensure skill_score is valid
            if not isinstance(skill_score, (int, float)) or skill_score < 0:
                print(f"Warning: Invalid calculated skill_score: {skill_score}, setting to 0")
                skill_score = 0

            timestamp = datetime.now(pytz.UTC).isoformat()
            
            record = {
                'user_id': user_id,
                'recent_skill': recent_skill,
                'peak_skill': peak_skill,
                'skill_match': skill_match,
                'confidence': confidence,
                'verdict': verdict,
                'skill_score': skill_score,
                'updated_at': timestamp
            }
            
            # Use upsert to handle both new and existing users
            response = self.client.table('leaderboard').upsert(record, on_conflict='user_id').execute()
            
            if response.data:
                print(f"Successfully updated leaderboard for user_id {user_id} with skill_score {skill_score:.2f}")
                
                # Update rank positions after successful upsert
                try:
                    self._update_leaderboard_ranks()
                except Exception as rank_error:
                    print(f"Warning: Failed to update ranks after leaderboard update: {rank_error}")
                    # Don't fail the whole operation if rank update fails
            else:
                print(f"Warning: No data returned from leaderboard upsert for user_id {user_id}")
                
        except Exception as e:
            print(f"Error updating leaderboard for user_id {user_id}: {e}")
            import traceback
            traceback.print_exc()

    def _update_leaderboard_ranks(self):
        """Update all rank positions using PostgreSQL window function"""
        try:
            # PostgreSQL query to update ranks using window function
            query = """
            UPDATE leaderboard 
            SET rank_position = ranked.rank
            FROM (
                SELECT id, 
                       ROW_NUMBER() OVER (ORDER BY skill_score DESC) as rank
                FROM leaderboard
            ) ranked
            WHERE leaderboard.id = ranked.id
            """
            
            # Execute raw SQL using RPC (Remote Procedure Call)
            response = self.client.rpc('update_leaderboard_ranks').execute()
            
        except Exception as e:
            print(f"Error updating leaderboard ranks: {e}")

    def get_leaderboard(self, limit: int = 50, search_query: str = None, verdict_filter: str = None) -> List[Dict]:
        """Get leaderboard with user info and analysis data, with optional search and filtering - OPTIMIZED"""
        try:
            # Single optimized query that joins all required data
            query = (self.client.table('leaderboard')
                    .select('''
                        rank_position,
                        recent_skill,
                        peak_skill,
                        skill_match,
                        confidence,
                        verdict,
                        skill_score,
                        updated_at,
                        user_id,
                        users (
                            osu_id,
                            username,
                            avatar_url,
                            rank,
                            pp
                        )
                    '''))
            
            # Add search filter
            if search_query:
                query = query.ilike('users.username', f'%{search_query}%')
            
            # Add verdict filter
            if verdict_filter and verdict_filter != 'all':
                query = query.eq('verdict', verdict_filter)
            
            # Execute query with ordering and limit
            response = query.order('skill_score', desc=True).limit(limit).execute()
            
            if not response.data:
                return []
            
            # Get all user IDs for batch analysis timestamp lookup
            user_ids = [row['user_id'] for row in response.data]
            
            # Batch query for analysis timestamps - single query for all users
            analysis_timestamps = {}
            try:
                # Get the most recent analysis timestamp for each user in a single query
                analysis_response = (self.client.table('analysis_results')
                                .select('user_id, created_at')
                                .in_('user_id', user_ids)
                                .order('created_at', desc=True)
                                .execute())
                
                # Group by user_id and get the most recent timestamp
                for row in analysis_response.data:
                    user_id = row['user_id']
                    if user_id not in analysis_timestamps:
                        analysis_timestamps[user_id] = row['created_at']
                        
            except Exception as e:
                print(f"Error getting batch analysis timestamps: {e}")
                # Continue with leaderboard update timestamps as fallback
            
            # Build results using batch-fetched data
            results = []
            for row in response.data:
                user_data = row['users']
                user_id = row['user_id']
                
                # Use batch-fetched analysis timestamp or fallback to leaderboard timestamp
                analysis_timestamp = analysis_timestamps.get(user_id, row['updated_at'])
                
                results.append({
                    'rank': row['rank_position'] or 0,
                    'osu_id': user_data['osu_id'],
                    'username': user_data['username'],
                    'avatar_url': user_data['avatar_url'],
                    'rank_global': user_data['rank'],
                    'pp': user_data['pp'],
                    'recent_skill': row['recent_skill'] or 0,
                    'peak_skill': row['peak_skill'] or 0,
                    'skill_match': row['skill_match'] or 0,
                    'confidence': row['confidence'] or 0,
                    'verdict': row['verdict'] or 'unknown',
                    'skill_score': row['skill_score'] or 0,
                    'analysis_timestamp': analysis_timestamp,
                    'updated_at': row['updated_at']
                })
            
            return results
            
        except Exception as e:
            print(f"Error getting leaderboard: {e}")
            return []

    def get_leaderboard_stats(self, verdict_filter: str = None) -> Dict:
        try:
            count_query = self.client.table('leaderboard').select('id', count='exact')
            if verdict_filter and verdict_filter != 'all':
                count_query = count_query.eq('verdict', verdict_filter)
            count_response = count_query.execute()
            total_players = count_response.count or 0

            data_query = self.client.table('leaderboard').select('recent_skill, confidence')
            if verdict_filter and verdict_filter != 'all':
                data_query = data_query.eq('verdict', verdict_filter)
            data_query = data_query.limit(1000)  # only for avg/top calc

            data_response = data_query.execute()
            data_rows = data_response.data or []

            skills = [row['recent_skill'] for row in data_rows if row['recent_skill']]
            confidences = [row['confidence'] for row in data_rows if row['confidence']]

            return {
                'total_players': total_players,  # ✅ now correct
                'avg_skill': sum(skills) / len(skills) if skills else 0,
                'top_skill': max(skills) if skills else 0,
                'avg_confidence': sum(confidences) / len(confidences) if confidences else 0
            }

        except Exception as e:
            print(f"Error getting leaderboard stats: {e}")
            return {'total_players': 0, 'avg_skill': 0, 'top_skill': 0, 'avg_confidence': 0}


    def get_user_stats(self) -> Dict:
        """Get database statistics - OPTIMIZED"""
        try:
            # Use connection pooling and batch queries
            from concurrent.futures import ThreadPoolExecutor
            import time
            
            def get_users_count():
                return self.client.table('users').select('id', count='exact').execute().count
            
            def get_analyses_count():
                return self.client.table('analysis_results').select('id', count='exact').execute().count
            
            def get_recent_analyses_count():
                seven_days_ago = (datetime.now(pytz.UTC) - timedelta(days=7)).isoformat()
                return (self.client.table('analysis_results')
                    .select('id', count='exact')
                    .gte('created_at', seven_days_ago)
                    .execute().count)
            
            # Execute queries in parallel with timeout
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    'total_users': executor.submit(get_users_count),
                    'total_analyses': executor.submit(get_analyses_count),
                    'recent_analyses': executor.submit(get_recent_analyses_count)
                }
                
                results = {}
                for key, future in futures.items():
                    try:
                        results[key] = future.result(timeout=5)  # 5 second timeout
                    except Exception as e:
                        print(f"Error getting {key}: {e}")
                        results[key] = 0
                
                return results
                
        except Exception as e:
            print(f"Error getting user stats: {e}")
            return {'total_users': 0, 'total_analyses': 0, 'recent_analyses': 0}


    
    def clear_old_analyses(self, days_old: int = 30):
        """Clear analyses older than specified days"""
        try:
            if days_old <= 0:
                raise ValueError("days_old must be greater than 0. Use wipe_all_analyses() for complete deletion.")
            
            # For cleanup operation with date filter
            cutoff_date = (datetime.now(pytz.UTC) - timedelta(days=days_old)).isoformat()
            print(f"Attempting to delete analyses older than {cutoff_date} ({days_old} days)")
            
            # First, check how many records would be deleted
            check_response = self.client.table('analysis_results').select('id', count='exact').lt('created_at', cutoff_date).execute()
            records_to_delete = check_response.count
            print(f"Found {records_to_delete} records to delete")
            
            if records_to_delete == 0:
                print("No old records found to delete")
                return 0
            
            # Delete the records
            response = self.client.table('analysis_results').delete().lt('created_at', cutoff_date).execute()
            
            # Verify deletion by checking the count again
            verify_response = self.client.table('analysis_results').select('id', count='exact').lt('created_at', cutoff_date).execute()
            remaining_old_records = verify_response.count
            actual_deleted = records_to_delete - remaining_old_records
            
            print(f"Successfully deleted {actual_deleted} old analysis records")
            return actual_deleted
            
        except Exception as e:
            print(f"Error clearing old analyses: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def wipe_all_analyses(self):
        """Wipe ALL analysis records from the database"""
        try:
            print("WIPING ALL analysis records from database")
            
            # First, check how many total records exist
            check_response = self.client.table('analysis_results').select('id', count='exact').execute()
            total_records = check_response.count
            print(f"Found {total_records} total records to wipe")
            
            if total_records == 0:
                print("No records found to wipe")
                return 0
            
            # Delete ALL records - using a condition that matches everything
            response = self.client.table('analysis_results').delete().neq('id', 0).execute()
            
            # Verify complete deletion
            verify_response = self.client.table('analysis_results').select('id', count='exact').execute()
            remaining_records = verify_response.count
            actual_deleted = total_records - remaining_records
            
            print(f"Successfully wiped {actual_deleted} analysis records")
            
            # Also clear the leaderboard since analyses are gone
            print("Clearing leaderboard entries...")
            leaderboard_response = self.client.table('leaderboard').delete().neq('id', 0).execute()
            print("Leaderboard cleared")
            
            return actual_deleted
            
        except Exception as e:
            print(f"Error wiping all analyses: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def get_analysis_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get analysis history for a user"""
        try:
            response = (self.client.table('analysis_results')
                       .select('recent_skill, peak_skill, skill_match, confidence, verdict, created_at')
                       .eq('user_id', user_id)
                       .order('created_at', desc=True)
                       .limit(limit)
                       .execute())
            
            results = []
            for row in response.data:
                results.append({
                    'recent_skill': row['recent_skill'],
                    'peak_skill': row['peak_skill'],
                    'skill_match': row['skill_match'],
                    'confidence': row['confidence'],
                    'verdict': row['verdict'],
                    'created_at': row['created_at']
                })
            return results
            
        except Exception as e:
            print(f"Error getting analysis history: {e}")
            return []

    def get_user_leaderboard_position(self, user_id: int) -> Optional[Dict]:
        """Get user's current leaderboard position"""
        try:
            response = (self.client.table('leaderboard')
                       .select('''
                            rank_position,
                            recent_skill,
                            peak_skill,
                            skill_match,
                            confidence,
                            verdict,
                            skill_score,
                            updated_at,
                            user_id,
                            users (
                                osu_id,
                                username,
                                avatar_url,
                                rank,
                                pp
                            )
                        ''')
                       .eq('user_id', user_id)
                       .execute())
            
            if response.data:
                row = response.data[0]
                return {
                    'rank': row['rank_position'],
                    'recent_skill': row['recent_skill'],
                    'peak_skill': row['peak_skill'],
                    'skill_match': row['skill_match'],
                    'confidence': row['confidence'],
                    'verdict': row['verdict'],
                    'skill_score': row['skill_score'],
                    'analysis_timestamp': row['updated_at'],
                    'username': row['users']['username'],
                    'avatar_url': row['users']['avatar_url'],
                    'rank_global': row['users']['rank'],
                    'pp': row['users']['pp']
                }
            return None
            
        except Exception as e:
            print(f"Error getting user leaderboard position: {e}")
            return None

    # Admin role methods
    def get_user_role(self, user_id: int) -> str:
        """Get user's role"""
        try:
            response = self.client.table('users').select('role').eq('id', user_id).execute()
            
            if response.data:
                return response.data[0].get('role', 'user')
            return 'user'
        except Exception as e:
            print(f"Error getting user role: {e}")
            return 'user'

    def is_user_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return self.get_user_role(user_id) == 'admin'

    def set_user_role(self, user_id: int, role: str) -> bool:
        """Set user's role (admin only operation)"""
        try:
            response = self.client.table('users').update({'role': role}).eq('id', user_id).execute()
            return bool(response.data)
        except Exception as e:
            print(f"Error setting user role: {e}")
            return False

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user by username"""
        try:
            response = self.client.table('users').select('*').eq('username', username).execute()
            
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error getting user by username {username}: {e}")
            return None
        
    def get_all_users(self) -> List[Dict]:
        """Fetch all users from the database"""
        try:
            response = self.client.table('users').select('id, username').execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error fetching all users: {e}")
            return []
