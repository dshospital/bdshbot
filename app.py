# --- PART 1: IMPORTS ---
import os
import json
import base64
from email.mime.text import MIMEText

# Flask imports for web server
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

# Database library that works with both PostgreSQL (Render) and MySQL (Local)
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

# --- Configuration will be read from Environment Variables on Render ---
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
RECIPIENT_EMAIL = 'marketing@daralshefa.com' 
GOOGLE_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbxNDYje0Ce2jTN_wFiZG_QsCDp1lAhsW_RHBJBK4EYOUtNW-DSHQJgaip8s32NyNcZk/exec'

# --- ✨ Smart Database Connection ---
# Render provides a DATABASE_URL. For local testing, we fall back to MySQL.
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    # Local MySQL connection string
    DATABASE_URL = "mysql+mysqlconnector://root:@localhost/test_db"

engine = create_engine(DATABASE_URL)

# --- PART 3: HELPER FUNCTIONS ---

def send_email_notification(name, phone, clinic):
    """Sends an email using Gmail API, reading secrets from environment variables."""
    creds = None
    
    token_data_str = os.environ.get('GOOGLE_TOKEN_JSON')
    creds_data_str = os.environ.get('GOOGLE_CREDENTIALS_JSON')

    if not creds_data_str:
        print("FATAL ERROR: GOOGLE_CREDENTIALS_JSON environment variable not set on Render.")
        return

    creds_data = json.loads(creds_data_str)

    if token_data_str:
        token_data = json.loads(token_data_str)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    
    if not creds or not creds.valid:
        print("Credentials not valid or expired. This needs manual intervention for the first run.")
        # On a server, you can't do the interactive flow. 
        # The token must be generated locally and its JSON content pasted into the environment variable.
        return

    try:
        service = build('gmail', 'v1', credentials=creds)
        html_body = f"""
        <html><body dir="rtl" style="font-family: Arial, sans-serif;">
            <h2>طلب موعد جديد عبر الشات بوت</h2>
            <p><strong>اسم المراجع:</strong> {name}</p>
            <p><strong>رقم الجوال:</strong> {phone}</p>
            <p><strong>العيادة المطلوبة:</strong> {clinic}</p>
        </body></html>
        """
        message = MIMEText(html_body, 'html')
        message['To'] = RECIPIENT_EMAIL
        message['Subject'] = f"طلب موعد جديد من: {name}"
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        send_message = (service.users().messages().send(userId="me", body=create_message).execute())
        print(F'Email sent successfully! Message Id: {send_message["id"]}')
    except Exception as e:
        print(f"An error occurred while sending email: {e}")

def send_to_google_sheet(name, phone, clinic):
    """Sends data to the Google Sheet."""
    try:
        payload = {"name": name, "phone": phone, "clinic": clinic}
        requests.post(GOOGLE_SCRIPT_URL, json=payload)
        print(f"Data sent to Google Sheet successfully.")
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
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/get_initial_data', methods=['GET'])
def get_initial_data():
    """Fetches the conversation tree from the database."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT intent_name, bot_response, question_examples FROM knowledge_base"))
            records = [dict(row) for row in result.mappings()]
            chat_tree = format_chat_tree(records)
            return jsonify(chat_tree)
    except Exception as e:
        print(f"Error fetching initial data: {e}")
        return jsonify({"error": "Could not connect to the database"}), 500

@app.route('/save_appointment', methods=['POST'])
def save_appointment():
    """Saves an appointment and triggers notifications."""
    data = request.get_json()
    name = data.get('name')
    phone = data.get('phone')
    clinic = data.get('clinic')
    
    send_email_notification(name, phone, clinic)
    send_to_google_sheet(name, phone, clinic)
    
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

@app.route('/save_approval', methods=['POST'])
def save_approval():
    """Saves a medical approval request."""
    data = request.get_json()
    try:
        with engine.connect() as conn:
            user_id = get_user_id(conn, data.get('platformId'))
            query = text("INSERT INTO medical_approvals (user_id, identity_number, phone_number, request_date) VALUES (:uid, :id, :phone, :date)")
            conn.execute(query, {"uid": user_id, "id": data.get('id_number'), "phone": data.get('phone'), "date": data.get('date')})
            conn.commit()
            return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error saving approval: {e}")
        return jsonify({"error": "Could not save approval"}), 500

# --- PART 5: RUN THE APP ---
if __name__ == '__main__':
    # This part is for local testing. Render uses the Procfile.
    app.run(debug=True, port=5000)
