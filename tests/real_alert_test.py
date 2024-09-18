import os
import sys
from dotenv import load_dotenv

# Add the 'src' directory to the system path
basedir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(basedir, '../src'))

# Load environment variables
load_dotenv(os.path.join(basedir, '../.env'))

# Import alerting functions
from alerting.alerting import send_telegram_alert, send_slack_alert, send_alert

def main():
    # Test sending a Telegram alert
    print("Sending Telegram alert...")
    send_telegram_alert("This is a real test message for Telegram!")

    # Test sending a Slack alert
    print("Sending Slack alert...")
    send_slack_alert("This is a real test message for Slack!")

    # Test sending combined alerts
    print("Sending combined alerts...")
    send_alert("This is a real test message for both Telegram and Slack!")

if __name__ == '__main__':
    main()
