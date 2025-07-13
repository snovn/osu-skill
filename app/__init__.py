import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev')

    # Register auth blueprint
    from app.auth.oauth import auth_bp
    app.register_blueprint(auth_bp)
    
    # Register analysis blueprint
    from app.routes.analysis import analysis_bp
    app.register_blueprint(analysis_bp)

    return app