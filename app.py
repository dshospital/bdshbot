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

# --- Database Connection ---
engine = None
if DATABASE_URL:
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    try:
        engine = create_engine(db_url)
        print("Database engine created successfully.")
    except Exception as e:
        print(f"FATAL ERROR: Could not create database engine. Check your DATABASE_URL format. Error: {e}")
else:
    print("FATAL ERROR: DATABASE_URL environment variable is not set.")

# --- PART 3: HELPER FUNCTIONS (No changes here) ---
# ... (All previous helper functions like send_email_notification, send_to_google_sheet, etc. remain here) ...

# --- PART 4: API ROUTES (ENDPOINTS) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_initial_data', methods=['GET'])
def get_initial_data():
    if not engine:
        return jsonify({"error": "Database is not configured."}), 500
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

# --- ✨ New Endpoint for Gemini API Calls with better logging ✨ ---
@app.route('/analyze_symptoms', methods=['POST'])
def analyze_symptoms():
    data = request.get_json()
    symptoms = data.get('symptoms')
    clinics_list = data.get('clinics', [])
    print(f"Received symptoms for analysis: {symptoms}")

    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY is not set in environment variables.")
        return jsonify({"error": "API key is not configured on the server."}), 500
    if not symptoms:
        return jsonify({"error": "No symptoms provided."}), 400

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""You are an expert medical triage assistant for a hospital in Saudi Arabia. A user has described their symptoms. Your task is to act like a real doctor:
    1. Analyze the symptoms provided.
    2. Based on the symptoms, determine the single most appropriate medical clinic for the user to visit from the provided list.
    3. Your response must be in Arabic and follow this exact format:
    "بناءً على الأعراض التي وصفتها، وهي: [List of symptoms], فإنني أوصي بزيارة **[Clinic Name]**. [Provide a brief, one-sentence explanation for why this clinic is suitable]."
    
    Example Response: "بناءً على الأعراض التي وصفتها، وهي: صداع وحرارة، فإنني أوصي بزيارة **عيادة الطب العام**. هذه العيادة هي الأنسب للتعامل مع الأعراض العامة والحمى."

    Available clinics: [{', '.join(clinics_list)}].
    User symptoms: "{symptoms}"
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        print("Sending request to Gemini API...")
        response = requests.post(api_url, json=payload, timeout=20)
        response.raise_for_status()
        
        result = response.json()
        print("Received response from Gemini API.")
        
        if "candidates" not in result or not result["candidates"]:
            print("Gemini API Error: No candidates in response.")
            raise ValueError("No candidates found in Gemini response.")
            
        recommendation = result["candidates"][0]["content"]["parts"][0]["text"]
        print(f"Recommendation: {recommendation}")
        return jsonify({"recommendation": recommendation})

    except requests.exceptions.RequestException as e:
        print(f"Gemini API request failed: {e}")
        return jsonify({"error": "Network error while contacting AI assistant."}), 500
    except (KeyError, IndexError, ValueError) as e:
        print(f"Error parsing Gemini response: {e}")
        print(f"Full Gemini Response: {result}")
        return jsonify({"error": "Invalid response from AI assistant."}), 500
    except Exception as e:
        print(f"An unexpected error occurred in analyze_symptoms: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to get analysis from AI assistant."}), 500

# ... (All other endpoints like save_appointment, etc. remain here) ...

# --- PART 5: RUN THE APP ---
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
