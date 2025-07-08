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
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') # ✨ New Secret

# --- Database Connection ---
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)

# --- PART 3: HELPER FUNCTIONS ---
# ... (All previous helper functions like send_email_notification, send_to_google_sheet, etc. remain here) ...

# --- PART 4: API ROUTES (ENDPOINTS) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_initial_data', methods=['GET'])
def get_initial_data():
    # ... (This function remains the same) ...
    pass

@app.route('/save_appointment', methods=['POST'])
def save_appointment():
    # ... (This function remains the same) ...
    pass

# --- ✨ New Endpoint for Gemini API Calls ✨ ---
@app.route('/analyze_symptoms', methods=['POST'])
def analyze_symptoms():
    data = request.get_json()
    symptoms = data.get('symptoms')
    clinics_list = data.get('clinics', [])

    if not GEMINI_API_KEY:
        return jsonify({"error": "API key is not configured on the server."}), 500
    if not symptoms:
        return jsonify({"error": "No symptoms provided."}), 400

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""You are an expert medical triage assistant for a hospital in Saudi Arabia. A user has described their symptoms. Your task is to act like a real doctor:
    1. Analyze the symptoms provided.
    2. Based on the symptoms, determine the single most appropriate medical clinic for the user to visit from the provided list.
    3. Your response must be in Arabic and follow this exact format:
    "بناءً على الأعراض التي وصفتها، وهي: [List of symptoms], فإنني أوصي بزيارة **[Clinic Name]**. [Provide a brief, one-sentence explanation for why this clinic is suitable]."
    
    Available clinics: [{', '.join(clinics_list)}].
    User symptoms: "{symptoms}"
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes
        result = response.json()
        recommendation = result.get("candidates")[0].get("content").get("parts")[0].get("text")
        return jsonify({"recommendation": recommendation})
    except Exception as e:
        print(f"Gemini API call failed: {e}")
        return jsonify({"error": "Failed to get analysis from AI assistant."}), 500


# ... (All other endpoints like save_insurance_inquiry, etc. remain here) ...

# --- PART 5: RUN THE APP ---
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
