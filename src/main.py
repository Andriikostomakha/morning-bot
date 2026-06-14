import logging
import os
from datetime import datetime
from rss_parser import fetch_news
from telegram_sender import send_telegram_message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not telegram_token or not telegram_chat_id:
        logger.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return

    logger.info(f"Starting morning bot at {datetime.now().isoformat()}")

    news_items = fetch_news(max_items=5)
    if not news_items:
        logger.warning("No news items fetched")
        return

    message = format_message(news_items)
    success = send_telegram_message(telegram_token, telegram_chat_id, message)

    if success:
        logger.info("Message sent!")
    else:
        logger.error("Failed to send message")

def format_message(news_items):
    text = "🌅 *Добрий ранок!*\n\n📰 *Топ-5 новин за ніч:*\n\n"
    for i, item in enumerate(news_items, 1):
        text += f"{i}. *{item['title']}*\n"
        text += f"   📍 {item['source']}\n"
        text += f"   🔗 [Читати далі]({item['link']})\n\n"
    return text

if __name__ == "__main__":
    main()
