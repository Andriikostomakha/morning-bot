import requests
import logging

logger = logging.getLogger(__name__)

def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': False
    }

    try:
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            logger.info("Message sent successfully!")
            return True
        else:
            logger.error(f"Telegram error: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error: {e}")
        return False
