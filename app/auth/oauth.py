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

    # Get user data using their own OAuth token
    user_response = requests.get('https://osu.ppy.sh/api/v2/me', headers={
        'Authorization': f'Bearer {access_token}'
    }).json()

    # Store user data AND their OAuth tokens
    session['username'] = user_response.get('username')
    session['avatar_url'] = user_response.get('avatar_url')
    session['user_id'] = user_response.get('id')
    session['access_token'] = access_token
    session['refresh_token'] = refresh_token
    session['token_expires_at'] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
    
    # Store the full user data to avoid additional API calls
    session['user_data'] = user_response

    return redirect('/dashboard')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.index'))