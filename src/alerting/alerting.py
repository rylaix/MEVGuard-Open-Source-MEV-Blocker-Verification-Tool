import os
import requests
from dotenv import load_dotenv
from utils import log, log_error

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path, override=True)

TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')

def send_telegram_alert(message):
    if not TELEGRAM_API_TOKEN or not TELEGRAM_CHAT_ID:
        log_error("Telegram API token or chat ID not configured.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID, 
        'text': message
        }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        log(f"Telegram alert sent: {message}")
    except requests.exceptions.RequestException as e:
        log_error(f"Failed to send Telegram alert: {e}")

def send_slack_alert(message):
    if not SLACK_WEBHOOK_URL:
        log_error("Slack webhook URL not configured.")
        return
    
    payload = {
        'text': message
        }
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        log(f"Slack alert sent: {message}")
    except requests.exceptions.RequestException as e:
        log_error(f"Failed to send Slack alert: {e}")

def send_alert(message):
    log(message)
    send_telegram_alert(message)
    send_slack_alert(message)
