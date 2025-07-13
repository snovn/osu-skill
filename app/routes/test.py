from flask import Blueprint, render_template, session, redirect, url_for

bp = Blueprint('auth', __name__)

@bp.route('/')
def index():
    return render_template('index.html', username=session.get('username'), user_avatar=session.get('avatar_url'))

@bp.route('/dashboard')
def dashboard():
    if not session.get('username'):
        return redirect(url_for('auth.index'))  # Or redirect to login route if exists
    
    # Placeholder dashboard data
    user_data = {
        'username': session.get('username'),
        'avatar_url': session.get('avatar_url'),
        'skill_match': '85%',
        'confidence': 'High',
        'verdict': 'Accurate',
        'recent_skill': 3200,
        'peak_skill': 3500,
        'insights': [
            "No retry spam detected",
            "Your top plays are recent",
            "Skill is consistent across mods"
        ]
    }
    
    return render_template('dashboard.html', **user_data)
