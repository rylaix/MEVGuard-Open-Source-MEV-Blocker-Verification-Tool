import os
import requests
from utils import log

TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')

def send_telegram_alert(message):
    if TELEGRAM_API_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }
        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                log(f"Telegram alert failed: {response.text}")
        except Exception as e:
            log(f"Error sending Telegram alert: {e}")

def send_slack_alert(message):
    if SLACK_WEBHOOK_URL:
        payload = {
            'text': message
        }
        try:
            response = requests.post(SLACK_WEBHOOK_URL, json=payload)
            if response.status_code != 200:
                log(f"Slack alert failed: {response.text}")
        except Exception as e:
            log(f"Error sending Slack alert: {e}")

def send_alert(message):
    log(message)
    send_telegram_alert(message)
    send_slack_alert(message)
