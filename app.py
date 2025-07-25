# --- PART 1: IMPORTS ---
import os
import json
import base64
from email.mime.text import MIMEText
import traceback

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

# --- Database Connection for Render ---
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
    creds = None
    token_data_str = os.environ.get('GOOGLE_TOKEN_JSON')
    creds_data_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')

    if not all([creds_data_str, token_data_str, recipient]):
        print("FATAL ERROR: Google credentials, token, or recipient email not set in environment variables.")
        return

    try:
        creds_data = json.loads(creds_data_str)
        token_data = json.loads(token_data_str)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        
        if not creds or not creds.valid:
            print("Credentials not valid or expired.")
            return

        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(html_body, 'html', 'utf-8')
        message['To'] = recipient
        message['Subject'] = subject
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        send_message = (service.users().messages().send(userId="me", body=create_message).execute())
        print(F'Email sent successfully to {recipient}! Message Id: {send_message["id"]}')
    except Exception as e:
        print(f"An error occurred while sending email: {e}")


def send_to_google_sheet(payload):
    """Sends any data payload to the Google Sheet."""
    try:
        if GOOGLE_SCRIPT_URL:
            requests.post(GOOGLE_SCRIPT_URL, json=payload)
            print(f"Data sent to Google Sheet successfully: {payload.get('type')}")
    except Exception as e:
        print(f"Failed to send data to Google Sheet: {e}")

def format_chat_tree(records):
    """Formats database records into the conversation tree structure."""
    chat_tree = {}
    for record in records:
        node_id = record.get('intent_name')
        message_text = record.get('bot_response')
        buttons_config = record.get('question_examples')
        buttons_json = []
        if buttons_config:
            buttons_list = buttons_config.strip().split(';')
            for button_item in buttons_list:
                if '->link:' in button_item:
                    parts = button_item.split('->link:')
                    buttons_json.append({"text": parts[0].strip(), "link": parts[1].strip()})
                elif '->' in button_item:
                    parts = button_item.split('->')
                    buttons_json.append({"text": parts[0].strip(), "goToID": parts[1].strip()})
        chat_tree[node_id] = {
            "MessageText": message_text,
            "MessageType": "buttons" if buttons_json else "text",
            "ButtonsJSON": buttons_json
        }
    return chat_tree

def get_user_id(conn, platform_id):
    """Gets a user's ID or creates a new user using SQLAlchemy."""
    user_query = text("SELECT user_id FROM users WHERE platform_user_id = :pid")
    result = conn.execute(user_query, {"pid": platform_id}).fetchone()
    
    if result:
        return result[0]
    else:
        insert_query = text("INSERT INTO users (platform_user_id) VALUES (:pid) RETURNING user_id")
        result = conn.execute(insert_query, {"pid": platform_id}).fetchone()
        conn.commit()
        return result[0]

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

@app.route('/save_appointment', methods=['POST'])
def save_appointment():
    data = request.get_json()
    name, phone, clinic = data.get('name'), data.get('phone'), data.get('clinic')
    
    subject = f"طلب موعد جديد من: {name}"
    html_body = f"<html><body><h2>طلب موعد جديد</h2><p><strong>الاسم:</strong> {name}</p><p><strong>الجوال:</strong> {phone}</p><p><strong>العيادة:</strong> {clinic}</p></body></html>"
    send_email_notification(subject, RECIPIENT_EMAIL, html_body)

    payload = {"type": "appointment", "name": name, "phone": phone, "clinic": clinic}
    send_to_google_sheet(payload)
    
    try:
        with engine.connect() as conn:
            user_id = get_user_id(conn, data.get('platformId'))
            query = text("INSERT INTO appointments (user_id, patient_name, patient_phone, clinic_name) VALUES (:uid, :name, :phone, :clinic)")
            conn.execute(query, {"uid": user_id, "name": name, "phone": phone, "clinic": clinic})
            conn.commit()
            return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error saving appointment: {e}")
        return jsonify({"error": "Could not save appointment"}), 500

@app.route('/save_insurance_inquiry', methods=['POST'])
def save_insurance_inquiry():
    data = request.get_json()
    phone, id_number, dob = data.get('phone'), data.get('id_number'), data.get('date')

    subject = "استعلام جديد عن تغطية تأمين"
    html_body = f"<html><body><h2>استعلام تأمين جديد</h2><p><strong>الجوال:</strong> {phone}</p><p><strong>رقم الهوية:</strong> {id_number}</p><p><strong>تاريخ الميلاد:</strong> {dob}</p></body></html>"
    send_email_notification(subject, INSURANCE_RECIPIENT_EMAIL, html_body)

    payload = {"type": "insurance_inquiry", "phone": phone, "id_number": id_number, "date": dob}
    send_to_google_sheet(payload)
    
    return jsonify({"status": "success"})

@app.route('/save_approval_inquiry', methods=['POST'])
def save_approval_inquiry():
    data = request.get_json()
    id_or_phone, request_date = data.get('id_or_phone'), data.get('request_date')

    subject = "استعلام جديد عن حالة موافقة طبية"
    html_body = f"<html><body><h2>استعلام جديد عن موافقة</h2><p><strong>رقم الهوية/الجوال:</strong> {id_or_phone}</p><p><strong>تاريخ الطلب:</strong> {request_date}</p></body></html>"
    send_email_notification(subject, APPROVAL_RECIPIENT_EMAIL, html_body)

    payload = {"type": "approval_inquiry", "id_or_phone": id_or_phone, "request_date": request_date}
    send_to_google_sheet(payload)

    try:
        with engine.connect() as conn:
            user_id = get_user_id(conn, data.get('platformId'))
            query = text("INSERT INTO medical_approvals (user_id, identity_number, request_date) VALUES (:uid, :id_phone, :date)")
            conn.execute(query, {"uid": user_id, "id_phone": id_or_phone, "date": request_date})
            conn.commit()
            return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error saving approval inquiry: {e}")
        return jsonify({"error": "Could not save approval inquiry"}), 500

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
        response = requests.post(api_url, json=payload, timeout=20)
        response.raise_for_status()
        result = response.json()
        recommendation = result.get("candidates")[0].get("content").get("parts")[0].get("text")
        return jsonify({"recommendation": recommendation})
    except Exception as e:
        print(f"Gemini API call failed: {e}")
        return jsonify({"error": "Failed to get analysis from AI assistant."}), 500

# --- PART 5: RUN THE APP ---
if __name__ == '__main__':
    # Render uses the Procfile. This is for local testing.
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
