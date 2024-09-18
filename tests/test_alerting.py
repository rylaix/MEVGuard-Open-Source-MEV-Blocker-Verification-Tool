import unittest
import os
import sys
from unittest.mock import patch
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path, override=True)

basedir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(basedir, '../src'))
from alerting.alerting import send_telegram_alert, send_slack_alert, send_alert

class TestAlertingSystem(unittest.TestCase):

    @patch.dict(os.environ, {
        'TELEGRAM_BOT_API_TOKEN': 'dummy_token',
        'TELEGRAM_CHAT_ID': '860341312',
        'SLACK_WEBHOOK_URL': 'dummy_url'
    })
    @patch('alerting.alerting.requests.post')
    def test_send_telegram_alert_success(self, mock_post):
        # Mock a successful Telegram API response
        mock_post.return_value.status_code = 200

        # Call the function
        send_telegram_alert("Test message")

        # Assert that the API was called with the correct URL and payload
        mock_post.assert_called_once_with(
            "https://api.telegram.org/botdummy_token/sendMessage",
            json={'chat_id': '860341312', 'text': 'Test message'}
        )

    @patch.dict(os.environ, {
        'TELEGRAM_BOT_API_TOKEN': 'dummy_token',
        'TELEGRAM_CHAT_ID': '860341312',
        'SLACK_WEBHOOK_URL': 'dummy_url'
    })
    @patch('alerting.alerting.requests.post')
    def test_send_telegram_alert_failure(self, mock_post):
        # Mock a failure response from Telegram API
        mock_post.return_value.status_code = 400
        mock_post.return_value.text = "Bad Request"

        # Call the function
        send_telegram_alert("Test message")

        # Assert that the API was called once even in case of failure
        mock_post.assert_called_once()

    @patch.dict(os.environ, {
        'SLACK_WEBHOOK_URL': 'dummy_url'
    })
    @patch('alerting.alerting.requests.post')
    def test_send_slack_alert_success(self, mock_post):
        # Mock a successful Slack webhook response
        mock_post.return_value.status_code = 200

        # Call the function
        send_slack_alert("Test message")

        # Assert that the webhook was called with the correct payload
        mock_post.assert_called_once_with(
            'dummy_url',
            json={'text': 'Test message'}
        )

    @patch.dict(os.environ, {
        'SLACK_WEBHOOK_URL': 'dummy_url'
    })
    @patch('alerting.alerting.requests.post')
    def test_send_slack_alert_failure(self, mock_post):
        # Mock a failure response from Slack webhook
        mock_post.return_value.status_code = 400
        mock_post.return_value.text = "Invalid Payload"

        # Call the function
        send_slack_alert("Test message")

        # Assert that the webhook was called once even in case of failure
        mock_post.assert_called_once()

    @patch('alerting.alerting.send_slack_alert')
    @patch('alerting.alerting.send_telegram_alert')
    def test_send_alert(self, mock_telegram, mock_slack):
        # Call the combined alert function
        send_alert("Test combined alert")

        # Assert both alerts are called
        mock_telegram.assert_called_once_with("Test combined alert")
        mock_slack.assert_called_once_with("Test combined alert")

if __name__ == '__main__':
    unittest.main()
