# --- PART 1: IMPORTS ---
import os
import json
import base64
from email.mime.text import MIMEText
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from sqlalchemy import create_engine, text
import requests 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- PART 2: FLASK APP AND CONFIGURATION ---
app = Flask(__name__, template_folder='templates')
CORS(app)

# --- Configuration is read from Environment Variables on Render ---
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL') 
INSURANCE_RECIPIENT_EMAIL = os.environ.get('INSURANCE_RECIPIENT_EMAIL')
APPROVAL_RECIPIENT_EMAIL = os.environ.get('APPROVAL_RECIPIENT_EMAIL')
GOOGLE_SCRIPT_URL = os.environ.get('GOOGLE_SCRIPT_URL')
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- ✨ New: Robust Database Connection Setup ✨ ---
# This check is critical. It ensures the DATABASE_URL is set in Render's environment.
if not DATABASE_URL:
    # This will cause the app to crash on startup if the variable is missing,
    # which is good because it makes the error obvious in Render's logs.
    raise ValueError("FATAL ERROR: DATABASE_URL environment variable is not set. Please check your Render service environment variables.")

# Fix for SQLAlchemy compatibility on Render
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    engine = create_engine(DATABASE_URL)
except Exception as e:
    print(f"FATAL ERROR: Could not create database engine. Check your DATABASE_URL format. Error: {e}")
    raise e

# --- PART 3: HELPER FUNCTIONS (No changes here) ---
def send_email_notification(subject, recipient, html_body): pass
def send_to_google_sheet(payload): pass
def format_chat_tree(records): pass
def get_user_id(conn, platform_id): pass
# (For brevity, the full code for the helper functions is omitted, but it should be the same as the previous version)


# --- PART 4: API ROUTES (No changes here) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_initial_data', methods=['GET'])
def get_initial_data():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT intent_name, bot_response, question_examples FROM knowledge_base"))
            records = [dict(row) for row in result.mappings()]
            if not records:
                return jsonify({"error": "Knowledge base is empty."}), 404
            chat_tree = format_chat_tree(records)
            return jsonify(chat_tree)
    except Exception as e:
        print(f"Error fetching initial data: {e}")
        return jsonify({"error": "Could not connect to the database"}), 500

# ... (All other routes like /save_appointment remain the same) ...


# --- PART 5: RUN THE APP ---
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
