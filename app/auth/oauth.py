# oauth.py - Enhanced version
import os
import requests
from flask import Blueprint, redirect, request, session, url_for, render_template
from dotenv import load_dotenv

load_dotenv()

auth_bp = Blueprint('auth', __name__)

OSU_CLIENT_ID = os.getenv('OSU_CLIENT_ID')
OSU_CLIENT_SECRET = os.getenv('OSU_CLIENT_SECRET')
REDIRECT_URI = 'http://osuskill.com/callback'

@auth_bp.route('/')
def index():
    # Render index page with username/avatar from session if logged in
    return render_template('index.html', username=session.get('username'), user_avatar=session.get('avatar_url'))


@auth_bp.route('/login')
def login():
    return redirect(
        f"https://osu.ppy.sh/oauth/authorize?client_id={OSU_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"
    )

@auth_bp.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Error: No code provided", 400

    token_response = requests.post('https://osu.ppy.sh/oauth/token', json={
        'client_id': OSU_CLIENT_ID,
        'client_secret': OSU_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI,
    }).json()

    access_token = token_response.get('access_token')
    refresh_token = token_response.get('refresh_token')
    expires_in = token_response.get('expires_in')
    
    if not access_token:
        return "Error retrieving access token", 400

    user_response = requests.get('https://osu.ppy.sh/api/v2/me', headers={
        'Authorization': f'Bearer {access_token}'
    }).json()

    # Store both user info and auth tokens
    session['username'] = user_response.get('username')
    session['avatar_url'] = user_response.get('avatar_url')
    session['user_id'] = user_response.get('id')
    session['access_token'] = access_token
    session['refresh_token'] = refresh_token
    session['token_expires_in'] = expires_in

    return redirect('/dashboard')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.index'))

# Helper function to refresh token if needed
def refresh_user_token():
    """Refresh user's access token if needed"""
    if 'refresh_token' not in session:
        return False
    
    try:
        token_response = requests.post('https://osu.ppy.sh/oauth/token', json={
            'client_id': OSU_CLIENT_ID,
            'client_secret': OSU_CLIENT_SECRET,
            'refresh_token': session['refresh_token'],
            'grant_type': 'refresh_token',
        }).json()
        
        access_token = token_response.get('access_token')
        refresh_token = token_response.get('refresh_token')
        expires_in = token_response.get('expires_in')
        
        if access_token:
            session['access_token'] = access_token
            session['refresh_token'] = refresh_token
            session['token_expires_in'] = expires_in
            return True
    except Exception as e:
        print(f"Error refreshing token: {e}")
    
    return False