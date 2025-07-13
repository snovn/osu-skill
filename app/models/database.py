import sqlite3
import json
import os
from datetime import datetime
import pytz
from typing import Dict, List, Optional
from contextlib import contextmanager

class Database:
    def __init__(self, db_path: str = 'osu_skillcheck.db'):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Enable dict-like access
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            print(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def init_database(self):
        """Initialize database tables"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Users table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        osu_id INTEGER UNIQUE NOT NULL,
                        username TEXT NOT NULL,
                        avatar_url TEXT,
                        rank INTEGER,
                        pp REAL,
                        playcount INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Analysis results table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS analysis_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        recent_skill REAL,
                        peak_skill REAL,
                        skill_match REAL,
                        confidence REAL,
                        verdict TEXT,
                        insights TEXT,
                        confidence_factors TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                
                # Cache table for API responses
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS api_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cache_key TEXT UNIQUE NOT NULL,
                        cache_data TEXT,
                        expires_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Leaderboard table - Fixed with proper constraints
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS leaderboard (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        recent_skill REAL DEFAULT 0,
                        peak_skill REAL DEFAULT 0,
                        skill_match REAL DEFAULT 0,
                        confidence REAL DEFAULT 0,
                        verdict TEXT DEFAULT 'unknown',
                        skill_score REAL DEFAULT 0,
                        rank_position INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id),
                        UNIQUE(user_id)
                    )
                ''')
                
                # Create indexes for better performance
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_leaderboard_skill_score 
                    ON leaderboard (skill_score DESC)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_leaderboard_user_id 
                    ON leaderboard (user_id)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_users_username 
                    ON users (username COLLATE NOCASE)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_users_osu_id 
                    ON users (osu_id)
                ''')
                
                conn.commit()
                print("Database initialized successfully")
        except Exception as e:
            print(f"Failed to initialize database: {e}")
            raise
    
    def get_user_by_osu_id(self, osu_id: int) -> Optional[Dict]:
        """Get user by osu ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, osu_id, username, avatar_url, rank, pp, playcount, created_at, updated_at
                    FROM users WHERE osu_id = ?
                ''', (osu_id,))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            print(f"Error getting user by osu_id {osu_id}: {e}")
            return None
    
    def upsert_user(self, user_data: Dict) -> Optional[int]:
        """Insert or update user data"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                existing_user = self.get_user_by_osu_id(user_data['id'])
                
                if existing_user:
                    # Update existing user
                    cursor.execute('''
                        UPDATE users 
                        SET username = ?, avatar_url = ?, rank = ?, pp = ?, playcount = ?, updated_at = ?
                        WHERE osu_id = ?
                    ''', (
                        user_data.get('username'),
                        user_data.get('avatar_url'),
                        user_data.get('statistics', {}).get('global_rank'),
                        user_data.get('statistics', {}).get('pp'),
                        user_data.get('statistics', {}).get('play_count'),
                        datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S'),
                        user_data['id']
                    ))
                    conn.commit()
                    print(f"Updated user {user_data.get('username')} (ID: {existing_user['id']})")
                    return existing_user['id']
                else:
                    # Insert new user
                    cursor.execute('''
                        INSERT INTO users (osu_id, username, avatar_url, rank, pp, playcount, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        user_data['id'],
                        user_data.get('username'),
                        user_data.get('avatar_url'),
                        user_data.get('statistics', {}).get('global_rank'),
                        user_data.get('statistics', {}).get('pp'),
                        user_data.get('statistics', {}).get('play_count'),
                        datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S'),
                        datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
                    ))
                    conn.commit()
                    user_id = cursor.lastrowid
                    print(f"Created new user {user_data.get('username')} (ID: {user_id})")
                    return user_id
        except Exception as e:
            print(f"Error upserting user: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_analysis_result(self, user_id: int, analysis_result: Dict) -> Optional[int]:
        """Save analysis result to database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Use explicit UTC timestamp
                timestamp = datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute('''
                    INSERT INTO analysis_results 
                    (user_id, recent_skill, peak_skill, skill_match, confidence, verdict, insights, confidence_factors, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    analysis_result.get('recent_skill', 0),
                    analysis_result.get('peak_skill', 0),
                    analysis_result.get('skill_match', 0),
                    analysis_result.get('confidence', 0),
                    analysis_result.get('verdict', 'unknown'),
                    json.dumps(analysis_result.get('insights', [])),
                    json.dumps(analysis_result.get('confidence_factors', {})),
                    timestamp
                ))
                conn.commit()
                analysis_id = cursor.lastrowid
                print(f"Saved analysis result (ID: {analysis_id}) for user_id: {user_id} at {timestamp}")
                return analysis_id
        except Exception as e:
            print(f"Error saving analysis result: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_latest_analysis(self, user_id: int) -> Optional[Dict]:
        """Get latest analysis result for user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT recent_skill, peak_skill, skill_match, confidence, verdict, insights, confidence_factors, created_at
                    FROM analysis_results 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT 1
                ''', (user_id,))
                
                row = cursor.fetchone()
                if row:
                    result = {
                        'recent_skill': row['recent_skill'],
                        'peak_skill': row['peak_skill'],
                        'skill_match': row['skill_match'],
                        'confidence': row['confidence'],
                        'verdict': row['verdict'],
                        'insights': json.loads(row['insights']) if row['insights'] else [],
                        'confidence_factors': json.loads(row['confidence_factors']) if row['confidence_factors'] else {},
                        'created_at': row['created_at']
                    }
                    print(f"Retrieved cached analysis for user_id {user_id}: {row['created_at']}")
                    return result
                else:
                    print(f"No cached analysis found for user_id {user_id}")
                    return None
        except Exception as e:
            print(f"Error getting latest analysis: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_leaderboard(self, user_id: int, analysis_result: Dict):
        """Update user's leaderboard position with full analysis data"""
        try:
            if not isinstance(analysis_result, dict):
                raise TypeError(f"Expected dict for analysis_result, got {type(analysis_result).__name__}")

            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Calculate skill score with proper default values
                recent_skill = analysis_result.get('recent_skill', 0) or 0
                peak_skill = analysis_result.get('peak_skill', 0) or 0
                skill_match = analysis_result.get('skill_match', 0) or 0
                confidence = analysis_result.get('confidence', 0) or 0
                verdict = analysis_result.get('verdict', 'unknown') or 'unknown'
                
                # Improved skill score calculation
                skill_score = (recent_skill * 0.7 + peak_skill * 0.3)
                
                timestamp = datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute('''
                    INSERT OR REPLACE INTO leaderboard 
                    (user_id, recent_skill, peak_skill, skill_match, confidence, verdict, skill_score, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id, 
                    recent_skill,
                    peak_skill,
                    skill_match,
                    confidence,
                    verdict,
                    skill_score,
                    timestamp
                ))
                
                # Update rank positions more efficiently
                self._update_leaderboard_ranks(cursor)
                
                conn.commit()
                print(f"Updated leaderboard for user_id {user_id} with skill_score {skill_score:.2f}")
        except Exception as e:
            print(f"Error updating leaderboard: {e}")
            import traceback
            traceback.print_exc()

    def _update_leaderboard_ranks(self, cursor):
        """Update all rank positions efficiently"""
        try:
            cursor.execute('''
                UPDATE leaderboard 
                SET rank_position = (
                    SELECT COUNT(*) 
                    FROM leaderboard l2 
                    WHERE l2.skill_score > leaderboard.skill_score
                ) + 1
            ''')
        except Exception as e:
            print(f"Error updating leaderboard ranks: {e}")

    def get_leaderboard(self, limit: int = 50, search_query: str = None, verdict_filter: str = None) -> List[Dict]:
        """Get leaderboard with user info and analysis data, with optional search and filtering"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build the query with optional filters
                base_query = '''
                    SELECT 
                        l.rank_position,
                        u.osu_id,
                        u.username,
                        u.avatar_url,
                        u.rank as rank_global,
                        u.pp,
                        l.recent_skill,
                        l.peak_skill,
                        l.skill_match,
                        l.confidence,
                        l.verdict,
                        l.skill_score,
                        l.updated_at
                    FROM leaderboard l
                    JOIN users u ON l.user_id = u.id
                '''
                
                conditions = []
                params = []
                
                # Add search filter
                if search_query:
                    conditions.append("u.username LIKE ?")
                    params.append(f"%{search_query}%")
                
                # Add verdict filter
                if verdict_filter and verdict_filter != 'all':
                    conditions.append("l.verdict = ?")
                    params.append(verdict_filter)
                
                # Add WHERE clause if we have conditions
                if conditions:
                    base_query += " WHERE " + " AND ".join(conditions)
                
                # Add ordering and limit
                base_query += " ORDER BY l.skill_score DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(base_query, params)
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'rank': row['rank_position'] or 0,
                        'osu_id': row['osu_id'],
                        'username': row['username'],
                        'avatar_url': row['avatar_url'],
                        'rank_global': row['rank_global'],
                        'pp': row['pp'],
                        'recent_skill': row['recent_skill'] or 0,
                        'peak_skill': row['peak_skill'] or 0,
                        'skill_match': row['skill_match'] or 0,
                        'confidence': row['confidence'] or 0,
                        'verdict': row['verdict'] or 'unknown',
                        'skill_score': row['skill_score'] or 0,
                        'updated_at': row['updated_at']
                    })
                return results
        except Exception as e:
            print(f"Error getting leaderboard: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_leaderboard_stats(self, verdict_filter: str = None) -> Dict:
        """Get leaderboard statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build base query for stats
                base_conditions = []
                params = []
                
                if verdict_filter and verdict_filter != 'all':
                    base_conditions.append("l.verdict = ?")
                    params.append(verdict_filter)
                
                where_clause = " WHERE " + " AND ".join(base_conditions) if base_conditions else ""
                
                # Total players
                cursor.execute(f'''
                    SELECT COUNT(*) as count 
                    FROM leaderboard l
                    JOIN users u ON l.user_id = u.id
                    {where_clause}
                ''', params)
                total_players = cursor.fetchone()['count']
                
                if total_players == 0:
                    return {
                        'total_players': 0,
                        'avg_skill': 0,
                        'top_skill': 0,
                        'avg_confidence': 0
                    }
                
                # Average skill
                cursor.execute(f'''
                    SELECT AVG(l.recent_skill) as avg_skill
                    FROM leaderboard l
                    JOIN users u ON l.user_id = u.id
                    {where_clause}
                ''', params)
                avg_skill = cursor.fetchone()['avg_skill'] or 0
                
                # Top skill
                cursor.execute(f'''
                    SELECT MAX(l.recent_skill) as top_skill
                    FROM leaderboard l
                    JOIN users u ON l.user_id = u.id
                    {where_clause}
                ''', params)
                top_skill = cursor.fetchone()['top_skill'] or 0
                
                # Average confidence
                cursor.execute(f'''
                    SELECT AVG(l.confidence) as avg_confidence
                    FROM leaderboard l
                    JOIN users u ON l.user_id = u.id
                    {where_clause}
                ''', params)
                avg_confidence = cursor.fetchone()['avg_confidence'] or 0
                
                return {
                    'total_players': total_players,
                    'avg_skill': avg_skill,
                    'top_skill': top_skill,
                    'avg_confidence': avg_confidence
                }
        except Exception as e:
            print(f"Error getting leaderboard stats: {e}")
            return {'total_players': 0, 'avg_skill': 0, 'top_skill': 0, 'avg_confidence': 0}
        
    def get_user_stats(self) -> Dict:
        """Get database statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Total users
                cursor.execute('SELECT COUNT(*) as count FROM users')
                total_users = cursor.fetchone()['count']
                
                # Total analyses
                cursor.execute('SELECT COUNT(*) as count FROM analysis_results')
                total_analyses = cursor.fetchone()['count']
                
                # Recent analyses (last 7 days)
                cursor.execute('''
                    SELECT COUNT(*) as count FROM analysis_results 
                    WHERE created_at > datetime('now', '-7 days')
                ''')
                recent_analyses = cursor.fetchone()['count']
                
                return {
                    'total_users': total_users,
                    'total_analyses': total_analyses,
                    'recent_analyses': recent_analyses
                }
        except Exception as e:
            print(f"Error getting user stats: {e}")
            return {'total_users': 0, 'total_analyses': 0, 'recent_analyses': 0}
    
    def clear_old_analyses(self, days_old: int = 30):
        """Clear analyses older than specified days"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM analysis_results 
                    WHERE created_at < datetime('now', '-{} days')
                '''.format(days_old))
                
                deleted_count = cursor.rowcount
                conn.commit()
                print(f"Deleted {deleted_count} old analysis records")
                return deleted_count
        except Exception as e:
            print(f"Error clearing old analyses: {e}")
            return 0
    
    def get_analysis_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get analysis history for a user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT recent_skill, peak_skill, skill_match, confidence, verdict, created_at
                    FROM analysis_results 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
                
                results = []
                for row in cursor.fetchall():
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
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        l.rank_position,
                        l.recent_skill,
                        l.peak_skill,
                        l.skill_match,
                        l.confidence,
                        l.verdict,
                        l.skill_score
                    FROM leaderboard l
                    WHERE l.user_id = ?
                ''', (user_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'rank': row['rank_position'],
                        'recent_skill': row['recent_skill'],
                        'peak_skill': row['peak_skill'],
                        'skill_match': row['skill_match'],
                        'confidence': row['confidence'],
                        'verdict': row['verdict'],
                        'skill_score': row['skill_score']
                    }
                return None
        except Exception as e:
            print(f"Error getting user leaderboard position: {e}")
            return None