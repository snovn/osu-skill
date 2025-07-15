from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from datetime import datetime, timedelta
from functools import wraps

import os
import sys
import threading
import time
import pytz

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.osu_client import OsuClient
from app.api.skill_analyzer import SkillAnalyzer
from app.models.database import SupabaseDatabase  # Changed from Database to SupabaseDatabase

analysis_bp = Blueprint('analysis', __name__)

# Global instances to avoid repeated initialization
_db = None
_osu_client = None
_analyzer = None
_lock = threading.Lock()

ADMIN_USERS = {
    'snovn',  # Replace with your actual osu! username
    # Add more admin usernames as needed
}
def is_admin(username=None):
    """Check if user is an admin"""
    if username is None:
        username = session.get('username')
    
    return username in ADMIN_USERS

def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        if not is_admin(session['username']):
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def get_components():
    """Get singleton instances of components"""
    global _db, _osu_client, _analyzer
    
    with _lock:
        if _db is None:
            _db = SupabaseDatabase()  # Changed from Database() to SupabaseDatabase()
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
        
        # Handle different timestamp formats - Supabase uses ISO format
        if 'T' in analysis_time_str:
            # ISO format with T separator
            if analysis_time_str.endswith('Z'):
                analysis_time_str = analysis_time_str.replace('Z', '+00:00')
            analysis_time = datetime.fromisoformat(analysis_time_str)
        else:
            # Fallback for other formats
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
                # CRITICAL FIX: Ensure leaderboard is updated with cached analysis
                db.update_leaderboard(user_id, cached_analysis)
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
        
        # CRITICAL FIX: Save analysis BEFORE updating leaderboard
        print(f"Saving analysis result for user_id: {user_id}")
        analysis_id = db.save_analysis_result(user_id, analysis_result)
        
        if not analysis_id:
            print("Failed to save analysis result")
            return render_template('dashboard.html',
                                 username=username,
                                 error="Failed to save analysis result")
        
        # Update leaderboard with the same analysis result
        print(f"Updating leaderboard for user_id: {user_id}")
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
    
    # Get query parameters for search and filtering
    search_query = request.args.get('search', '')
    verdict_filter = request.args.get('verdict', 'all')
    
    # Get leaderboard data with filters
    limit = request.args.get('limit', 50, type=int)
    leaderboard_data = db.get_leaderboard(limit, search_query, verdict_filter)

        
    # Get database stats
    stats = db.get_user_stats()
    
    # Get leaderboard stats with filter
    leaderboard_stats = db.get_leaderboard_stats(verdict_filter)
    
    return render_template(
        'leaderboard.html',
        leaderboard=leaderboard_data,
        stats=stats,
        leaderboard_stats=leaderboard_stats,
        search_query=search_query,
        verdict_filter=verdict_filter,
        username=session.get('username'),
        user_avatar=session.get('avatar_url')
    )

@analysis_bp.route('/api/leaderboard')
def api_leaderboard():
    """API endpoint for leaderboard data"""
    db, _, _ = get_components()
    limit = request.args.get('limit', 50, type=int)
    search_query = request.args.get('search', '')
    verdict_filter = request.args.get('verdict', 'all')
    
    leaderboard_data = db.get_leaderboard(limit, search_query, verdict_filter)
    
    # Get leaderboard stats
    leaderboard_stats = db.get_leaderboard_stats(verdict_filter)
    
    return jsonify({
        'leaderboard': leaderboard_data,
        'stats': leaderboard_stats,
        'total_entries': len(leaderboard_data),
        'filters': {
            'search': search_query,
            'verdict': verdict_filter
        }
    })

@analysis_bp.route('/api/status')
def api_status():
    """API endpoint for system status"""
    db, osu_client, _ = get_components()
    
    try:
        # Test database connection by getting stats
        stats = db.get_user_stats()
        
        # Test osu! API connection
        api_status = osu_client.get_client_credentials_token()
        
        # Get cache stats if available
        cache_stats = getattr(osu_client, 'get_cache_stats', lambda: {})()
        
        return jsonify({
            'database': {
                'connected': True,
                'stats': stats
            },
            'osu_api': {
                'connected': bool(api_status),
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

# Additional API routes for enhanced functionality

@analysis_bp.route('/api/user/<username>/history')
def api_user_history(username):
    """API endpoint to get user's analysis history"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Security: Only allow users to access their own history
    if session['username'] != username:
        return jsonify({'error': 'Access denied'}), 403
    
    db, osu_client, _ = get_components()
    
    try:
        user_info = osu_client.get_user_info(username)
        if not user_info:
            return jsonify({'error': 'User not found'}), 404
        
        user_id = db.upsert_user(user_info)
        history = db.get_analysis_history(user_id, 10)
        
        return jsonify({
            'username': username,
            'history': history,
            'total_entries': len(history)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/api/user/<username>/position')
def api_user_position(username):
    """API endpoint to get user's leaderboard position"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    db, osu_client, _ = get_components()
    
    try:
        user_info = osu_client.get_user_info(username)
        if not user_info:
            return jsonify({'error': 'User not found'}), 404
        
        user_id = db.upsert_user(user_info)
        position = db.get_user_leaderboard_position(user_id)
        
        return jsonify({
            'username': username,
            'position': position
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/api/admin/cleanup')
@admin_required
def api_cleanup():
    """API endpoint to clean up old analyses (admin only)"""
    db, _, _ = get_components()
    
    try:
        days_old = request.args.get('days', 30, type=int)
        
        # Validate days_old parameter
        if days_old <= 0:
            return jsonify({
                'error': 'days parameter must be greater than 0. Use /api/admin/wipe for complete deletion.'
            }), 400
        
        deleted_count = db.clear_old_analyses(days_old)
        
        return jsonify({
            'deleted_count': deleted_count,
            'days_old': days_old,
            'operation': 'cleanup',
            'timestamp': datetime.now(pytz.UTC).isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/api/admin/wipe')
@admin_required
def api_wipe():
    """API endpoint to wipe ALL analyses (admin only)"""
    db, _, _ = get_components()

    try:
        deleted_count = db.wipe_all_analyses()
        
        return jsonify({
            'deleted_count': deleted_count,
            'operation': 'wipe',
            'wiped_all': True,
            'timestamp': datetime.now(pytz.UTC).isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analysis_bp.route('/api/admin/force_reanalyze/<username>')
@admin_required
def force_reanalyze_user(username):
    db, osu_client, analyzer = get_components()
    user_info = osu_client.get_user_info(username)
    if not user_info:
        return jsonify({'error': 'User not found'}), 404
    user_id = db.upsert_user(user_info)
    user_data = osu_client.get_comprehensive_user_data(username)
    analysis = analyzer.analyze_user_skill(user_data)
    db.save_analysis_result(user_id, analysis)
    db.update_leaderboard(user_id, analysis)
    return jsonify({'success': True, 'verdict': analysis['verdict']})