# --- PART 1: IMPORTS ---
import os
import json
import base64
import traceback
from email.mime.text import MIMEText

# Flask imports for web server
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

# Database library that works with PostgreSQL
from sqlalchemy import create_engine, text

# For Google Sheets and other HTTP requests
import requests 

# For Gmail API
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
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- ✨ Robust Database Connection - THIS IS THE FIX ✨ ---
engine = None
try:
    if not DATABASE_URL:
        raise ValueError("FATAL ERROR: DATABASE_URL environment variable is not set.")
    
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(db_url)
    print("Database engine created successfully.")
except Exception as e:
    print(f"FATAL ERROR: Could not create database engine. Check your DATABASE_URL. Error: {e}")
    traceback.print_exc()

# --- PART 3: HELPER FUNCTIONS ---

def send_email_notification(subject, recipient, html_body):
    """Generic function to send an email using Gmail API."""
    # ... (This function remains the same) ...
    pass

def send_to_google_sheet(payload):
    """Sends any data payload to the Google Sheet."""
    # ... (This function remains the same) ...
    pass

def format_chat_tree(records):
    """Formats database records into the conversation tree structure."""
    # ... (This function remains the same) ...
    pass

def get_user_id(conn, platform_id):
    """Gets a user's ID or creates a new user using SQLAlchemy."""
    # ... (This function remains the same) ...
    pass

# --- PART 4: API ROUTES (ENDPOINTS) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_initial_data', methods=['GET'])
def get_initial_data():
    """Fetches the conversation tree from the database."""
    print("--- Request received for /get_initial_data ---")
    if not engine:
        print("Database engine is not available.")
        return jsonify({"error": "Database connection is not configured."}), 500
    try:
        with engine.connect() as conn:
            print("Database connection successful.")
            result = conn.execute(text("SELECT intent_name, bot_response, question_examples FROM knowledge_base"))
            records = [dict(row) for row in result.mappings()]
            print(f"Found {len(records)} records in knowledge_base.")
            
            if not records:
                print("Knowledge base is empty. Returning 404.")
                return jsonify({"error": "Knowledge base is empty."}), 404
            
            chat_tree = format_chat_tree(records)
            print("Successfully formatted chat tree. Returning data.")
            return jsonify(chat_tree)
            
    except Exception as e:
        print(f"---!!! AN ERROR OCCURRED in /get_initial_data !!!---")
        print(f"Error details: {e}")
        traceback.print_exc()
        return jsonify({"error": "An internal server error occurred while connecting to the database."}), 500

# ... (All other routes like /save_appointment remain the same) ...

# --- PART 5: RUN THE APP ---
if __name__ == '__main__':
    # This part is for local testing. Render uses the Procfile.
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
