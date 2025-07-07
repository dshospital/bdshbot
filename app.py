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

# --- Configuration is read from Environment Variables on Render ---
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'marketing@daralshefa.com') 
GOOGLE_SCRIPT_URL = os.environ.get('GOOG
