from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from datetime import datetime, timedelta
import os
import sys
import threading
import time
import pytz

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.osu_client import OsuClient
from app.api.skill_analyzer import SkillAnalyzer
from app.models.database import Database

analysis_bp = Blueprint('analysis', __name__)

# Global instances to avoid repeated initialization
_db = None
_osu_client = None
_analyzer = None
_lock = threading.Lock()

def get_components():
    """Get singleton instances of components"""
    global _db, _osu_client, _analyzer
    
    with _lock:
        if _db is None:
            _db = Database()
        if _osu_client is None:
            _osu_client = OsuClient()
        if _analyzer is None:
            _analyzer = SkillAnalyzer()
    
    return _db, _osu_client, _analyzer

def is_cache_valid(cached_analysis, cache_duration_minutes=30):
    """Check if cached analysis is still valid"""
    if not cached_analysis or not cached_analysis.get('created_at'):
        return False
    
    try:
        # Parse the timestamp from database
        analysis_time_str = cached_analysis['created_at']
        
        # Handle different timestamp formats
        if 'T' in analysis_time_str:
            # ISO format with T separator
            if analysis_time_str.endswith('Z'):
                analysis_time_str = analysis_time_str.replace('Z', '+00:00')
            analysis_time = datetime.fromisoformat(analysis_time_str)
        else:
            # SQLite datetime format
            analysis_time = datetime.strptime(analysis_time_str, '%Y-%m-%d %H:%M:%S')
        
        # Make sure we're comparing timezone-aware datetimes
        if analysis_time.tzinfo is None:
            analysis_time = analysis_time.replace(tzinfo=pytz.UTC)
        
        current_time = datetime.now(pytz.UTC)
        time_diff = current_time - analysis_time
        
        is_valid = time_diff < timedelta(minutes=cache_duration_minutes)
        
        print(f"Cache check: Analysis time: {analysis_time}, Current time: {current_time}")
        print(f"Time difference: {time_diff}, Cache valid: {is_valid}")
        
        return is_valid
        
    except (ValueError, TypeError) as e:
        print(f"Error parsing cache timestamp: {e}")
        return False

@analysis_bp.route('/dashboard')
def dashboard():
    """Dashboard route - shows analysis results"""
    if 'username' not in session:
        return redirect(url_for('auth.login'))
    
    username = session.get('username')
    db, osu_client, analyzer = get_components()
    
    try:
        # Get user info first
        print(f"Fetching user info for {username}...")
        user_info = osu_client.get_user_info(username)
        if not user_info:
            return render_template('dashboard.html', 
                                 username=username,
                                 error="Could not fetch user data from osu! API")
        
        # Save/update user in database
        user_id = db.upsert_user(user_info)
        if not user_id:
            print("Failed to save user to database")
            return render_template('dashboard.html',
                                 username=username,
                                 error="Failed to save user data")
        
        # Check for cached analysis
        print(f"Checking cache for user_id: {user_id}")
        cached_analysis = db.get_latest_analysis(user_id)
        
        if cached_analysis:
            print(f"Found cached analysis: {cached_analysis.get('created_at')}")
            if is_cache_valid(cached_analysis, 30):  # 30 minutes cache
                print("Using cached analysis")
                return render_template('dashboard.html',
                                     username=username,
                                     user_info=user_info,
                                     analysis=cached_analysis,
                                     from_cache=True)
            else:
                print("Cache expired, performing new analysis")
        else:
            print("No cached analysis found, performing new analysis")
        
        # Perform new analysis
        print(f"Starting comprehensive analysis for {username}...")
        start_time = time.time()
        
        # Get comprehensive data
        user_data = osu_client.get_comprehensive_user_data(username)
        
        if not user_data or not user_data.get('user_info'):
            return render_template('dashboard.html',
                                 username=username,
                                 error="Could not fetch comprehensive user data")
        
        # Perform analysis
        analysis_result = analyzer.analyze_user_skill(user_data)
        
        if not analysis_result:
            return render_template('dashboard.html',
                                 username=username,
                                 error="Failed to analyze user skill")
        
        # Save analysis result with explicit commit
        print(f"Saving analysis result for user_id: {user_id}")
        analysis_id = db.save_analysis_result(user_id, analysis_result)
        
        if analysis_id:
            print(f"Analysis saved with ID: {analysis_id}")
        else:
            print("Failed to save analysis result")
        
        # Update leaderboard
        db.save_analysis_result(user_id, analysis_result)

        # Update leaderboard
        db.update_leaderboard(user_id, analysis_result)


        
        print(f"Analysis completed in {time.time() - start_time:.2f} seconds")
        
        # Add timestamp to analysis result for template
        analysis_result['created_at'] = datetime.now(pytz.UTC).isoformat()
        
        return render_template('dashboard.html',
                             username=username,
                             user_info=user_data['user_info'],
                             analysis=analysis_result,
                             from_cache=False)
    
    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        import traceback
        traceback.print_exc()
        return render_template('dashboard.html',
                             username=username,
                             error=f"Error loading dashboard: {str(e)}")


@analysis_bp.route('/analyze')
def analyze_user():
    """Redirect to dashboard - analysis is now handled there"""
    return redirect(url_for('analysis.dashboard'))

@analysis_bp.route('/api/analyze/<username>')
def api_analyze(username):
    """API endpoint for skill analysis"""
    if 'username' not in session:
        return redirect(url_for('auth.login'))
    
    db, osu_client, analyzer = get_components()
    
    try:
        # Check for recent analysis first
        user_info = osu_client.get_user_info(username)
        if not user_info:
            return jsonify({'error': 'User not found'}), 404
        
        user_id = db.upsert_user(user_info)
        
        # Check cache
        cached_analysis = db.get_latest_analysis(user_id)
        if cached_analysis and is_cache_valid(cached_analysis, 30):
            return jsonify({
                'user_info': user_info,
                'analysis': cached_analysis,
                'timestamp': cached_analysis['created_at'],
                'from_cache': True
            })
        
        # Perform new analysis
        user_data = osu_client.get_comprehensive_user_data(username)
        
        if not user_data or not user_data.get('user_info'):
            return jsonify({'error': 'Could not fetch comprehensive user data'}), 404
        
        # Perform analysis
        analysis_result = analyzer.analyze_user_skill(user_data)
        
        # Save analysis result
        db.save_analysis_result(user_id, analysis_result)
        
        # Update leaderboard
        # Save analysis result
        db.save_analysis_result(user_id, analysis_result)

        # Update leaderboard
        db.update_leaderboard(user_id, analysis_result)

        
        return jsonify({
            'user_info': user_data['user_info'],
            'analysis': analysis_result,
            'timestamp': datetime.now(pytz.UTC).isoformat(),
            'from_cache': False
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analysis_bp.route('/leaderboard')
def leaderboard():
    """Show leaderboard page"""
    db, _, _ = get_components()
    
    # Get leaderboard data
    leaderboard_data = db.get_leaderboard(50)
    
    # Get database stats
    stats = db.get_user_stats()
    
    return render_template('leaderboard.html',
                         leaderboard=leaderboard_data,
                         stats=stats,
                         username=session.get('username'))

@analysis_bp.route('/api/leaderboard')
def api_leaderboard():
    """API endpoint for leaderboard data"""
    db, _, _ = get_components()
    limit = request.args.get('limit', 50, type=int)
    
    leaderboard_data = db.get_leaderboard(limit)
    
    # Calculate stats
    if leaderboard_data:
        total_players = len(leaderboard_data)
        avg_skill = sum(p['recent_skill'] for p in leaderboard_data) / total_players
        top_skill = max(p['recent_skill'] for p in leaderboard_data)
        avg_confidence = sum(p['confidence'] for p in leaderboard_data) / total_players
    else:
        total_players = avg_skill = top_skill = avg_confidence = 0
    
    return jsonify({
        'leaderboard': leaderboard_data,
        'stats': {
            'total_players': total_players,
            'avg_skill': avg_skill,
            'top_skill': top_skill,
            'avg_confidence': avg_confidence
        },
        'total_entries': len(leaderboard_data)
    })

@analysis_bp.route('/api/status')
def api_status():
    """API endpoint for system status"""
    db, osu_client, _ = get_components()
    
    try:
        # Test database connection
        stats = db.get_user_stats()
        
        # Test osu! API connection
        api_status = osu_client.get_client_credentials_token()
        
        # Get cache stats
        cache_stats = osu_client.get_cache_stats()
        
        return jsonify({
            'database': {
                'connected': True,
                'stats': stats
            },
            'osu_api': {
                'connected': api_status,
                'cache_stats': cache_stats
            },
            'timestamp': datetime.now(pytz.UTC).isoformat()
        })
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now(pytz.UTC).isoformat()
        }), 500

# Debug route to check cache status
@analysis_bp.route('/debug/cache/<username>')
def debug_cache(username):
    """Debug route to check cache status - only allows access to own data"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # SECURITY: Only allow users to access their own cache data
    if session['username'] != username:
        return jsonify({'error': 'Access denied - can only view your own cache data'}), 403
    
    db, osu_client, _ = get_components()
    
    try:
        user_info = osu_client.get_user_info(username)
        if not user_info:
            return jsonify({'error': 'User not found'}), 404
        
        user_id = db.upsert_user(user_info)
        cached_analysis = db.get_latest_analysis(user_id)
        
        if cached_analysis:
            cache_valid = is_cache_valid(cached_analysis, 30)
            return jsonify({
                'user_id': user_id,
                'has_cache': True,
                'cache_timestamp': cached_analysis.get('created_at'),
                'cache_valid': cache_valid,
                'cache_data': cached_analysis
            })
        else:
            return jsonify({
                'user_id': user_id,
                'has_cache': False,
                'cache_valid': False
            })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500