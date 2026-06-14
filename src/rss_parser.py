import feedparser
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    {'url': 'https://kyivindependent.com/feed', 'source': 'Kyiv Independent 🇺🇦'},
    {'url': 'https://www.ukrinform.net/rss/block-lastnews', 'source': 'Ukrinform 🇺🇦'},
    {'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'source': 'BBC World 🌍'},
    {'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'source': 'Al Jazeera 🌍'},
]

def fetch_news(max_items=5):
    all_items = []

    for feed_config in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_config['url'])
            for entry in feed.entries[:5]:
                all_items.append({
                    'title': entry.get('title', 'No title'),
                    'link': entry.get('link', '#'),
                    'source': feed_config['source'],
                })
                if len(all_items) >= max_items * 2:
                    break
        except Exception as e:
            logger.error(f"Error fetching {feed_config['source']}: {e}")
            continue

    return all_items[:max_items]
