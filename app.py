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
APPROVAL_RECIPIENT_EMAIL = os.environ.get('APPROVAL_RECIPIENT_EMAIL') # ✨ New
GOOGLE_SCRIPT_URL = os.environ.get('GOOGLE_SCRIPT_URL')
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)

# --- PART 3: HELPER FUNCTIONS ---

def send_email_notification(subject, recipient, html_body):
    # ... (This function remains the same)
    pass

def send_to_google_sheet(payload):
    # ... (This function remains the same)
    pass

def format_chat_tree(records):
    # ... (This function remains the same)
    pass

def get_user_id(conn, platform_id):
    # ... (This function remains the same)
    pass

# --- PART 4: API ROUTES (ENDPOINTS) ---

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

# --- ✨ New Endpoint for Approval Status Inquiries ✨ ---
@app.route('/save_approval_inquiry', methods=['POST'])
def save_approval_inquiry():
    data = request.get_json()
    id_or_phone = data.get('id_or_phone')
    request_date = data.get('request_date')

    # Send email notification to approvals department
    subject = "استعلام جديد عن حالة موافقة طبية"
    html_body = f"<html><body><h2>استعلام جديد عن موافقة</h2><p><strong>رقم الهوية/الجوال:</strong> {id_or_phone}</p><p><strong>تاريخ الطلب:</strong> {request_date}</p></body></html>"
    send_email_notification(subject, APPROVAL_RECIPIENT_EMAIL, html_body)

    # Send to Google Sheet
    payload = {"type": "approval_inquiry", "id_or_phone": id_or_phone, "request_date": request_date}
    send_to_google_sheet(payload)

    try:
        with engine.connect() as conn:
            user_id = get_user_id(conn, data.get('platformId'))
            # We save this in the 'medical_approvals' table for now
            query = text("INSERT INTO medical_approvals (user_id, identity_number, request_date) VALUES (:uid, :id_phone, :date)")
            conn.execute(query, {"uid": user_id, "id_phone": id_or_phone, "date": request_date})
            conn.commit()
            return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error saving approval inquiry: {e}")
        return jsonify({"error": "Could not save approval inquiry"}), 500

# --- PART 5: RUN THE APP ---
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
