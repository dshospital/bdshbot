# --- ✨ PART 1: IMPORTS ✨ ---
# Flask imports for web server
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

# Database connector
import mysql.connector
from mysql.connector import Error

# For Google Sheets and other HTTP requests
import requests 

# For Gmail API
import os.path
import base64
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- ✨ PART 2: FLASK APP AND CONFIGURATION ✨ ---
app = Flask(__name__, template_folder='templates') # Tell Flask where to find index.html
CORS(app)

# --- ضع إعداداتك الخاصة هنا ---
# This scope allows us to send emails only, not read or delete them
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
RECIPIENT_EMAIL = 'marketing@daralshefa.com' # بريد القسم المختص
GOOGLE_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbxNDYje0Ce2jTN_wFiZG_QsCDp1lAhsW_RHBJBK4EYOUtNW-DSHQJgaip8s32NyNcZk/exec' # رابط جوجل شيت
DB_CONFIG = { 'host': 'localhost', 'user': 'root', 'password': '', 'database': 'test_db' }
# ---------------------------------

# --- ✨ PART 3: HELPER FUNCTIONS ✨ ---

def create_connection():
    """Creates a secure connection to the database."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def send_email_notification(name, phone, clinic):
    """Sends an email using the Gmail API."""
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # credentials.json is the file you downloaded from Google Cloud
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

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
    except HttpError as error:
        print(f'An HTTP error occurred while sending email: {error}')
    except Exception as e:
        print(f"A general error occurred while sending email: {e}")

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
    """Gets a user's ID or creates a new user."""
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE platform_user_id = %s", (platform_id,))
    user = cursor.fetchone()
    if user:
        user_id = user[0]
    else:
        cursor.execute("INSERT INTO users (platform_user_id) VALUES (%s)", (platform_id,))
        user_id = cursor.lastrowid
    conn.commit()
    return user_id

# --- ✨ PART 4: API ROUTES (ENDPOINTS) ✨ ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/get_initial_data', methods=['GET'])
def get_initial_data():
    """Fetches the conversation tree from the database."""
    conn = create_connection()
    if not conn: return jsonify({"error": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT intent_name, bot_response, question_examples FROM knowledge_base")
        records = cursor.fetchall()
        chat_tree = format_chat_tree(records)
        return jsonify(chat_tree)
    finally:
        if conn and conn.is_connected(): conn.close()

@app.route('/save_appointment', methods=['POST'])
def save_appointment():
    """Saves an appointment and triggers notifications."""
    data = request.get_json()
    name = data.get('name')
    phone = data.get('phone')
    clinic = data.get('clinic')
    
    # Run background tasks
    send_email_notification(name, phone, clinic)
    send_to_google_sheet(name, phone, clinic)
    
    conn = create_connection()
    if not conn: return jsonify({"error": "Database connection failed"}), 500
    try:
        user_id = get_user_id(conn, data.get('platformId'))
        cursor = conn.cursor()
        query = "INSERT INTO appointments (user_id, patient_name, patient_phone, clinic_name) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (user_id, name, phone, clinic))
        conn.commit()
        return jsonify({"status": "success"})
    finally:
        if conn and conn.is_connected(): conn.close()

@app.route('/save_approval', methods=['POST'])
def save_approval():
    """Saves a medical approval request."""
    data = request.get_json()
    conn = create_connection()
    if not conn: return jsonify({"error": "Database connection failed"}), 500
    try:
        user_id = get_user_id(conn, data.get('platformId'))
        cursor = conn.cursor()
        query = "INSERT INTO medical_approvals (user_id, identity_number, phone_number, request_date) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (user_id, data.get('id_number'), data.get('phone'), data.get('date')))
        conn.commit()
        return jsonify({"status": "success"})
    finally:
        if conn and conn.is_connected(): conn.close()

@app.route('/save_message', methods=['POST'])
def save_message():
    """Saves general messages (can be expanded later)."""
    data = request.get_json()
    conn = create_connection()
    if not conn: return jsonify({"error": "Database connection failed"}), 500
    try:
        user_id = get_user_id(conn, data.get('platformId'))
        # Logic to save general messages can be added here
        return jsonify({"status": "message saved"})
    finally:
        if conn and conn.is_connected(): conn.close()

# --- ✨ PART 5: RUN THE APP ✨ ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)
