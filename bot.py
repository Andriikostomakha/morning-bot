import logging
import os
import re
import threading
from datetime import datetime, time, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

import feedparser
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN        = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID      = int(os.getenv('TELEGRAM_CHAT_ID', '0'))
ALERTS_KEY   = os.getenv('ALERTS_API_KEY', '')
reminders    = {}
alert_active = False

RSS_FEEDS = [
    {'url': 'https://kyivindependent.com/feed',             'source': 'Kyiv Independent 🇺🇦'},
    {'url': 'https://www.ukrinform.net/rss/block-lastnews', 'source': 'Ukrinform 🇺🇦'},
    {'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',   'source': 'BBC World 🌍'},
]

# ── Веб-сервер ───────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, *a): pass

def web():
    port = int(os.getenv('PORT', 8080))
    HTTPServer(('0.0.0.0', port), HealthHandler).serve_forever()

# ── Новини ───────────────────────────────────────────────
async def fetch_news(bot, chat_id):
    items = []
    for feed in RSS_FEEDS:
        try:
            f = feedparser.parse(feed['url'])
            for e in f.entries[:2]:
                items.append({
                    'title':  e.get('title', ''),
                    'link':   e.get('link', ''),
                    'source': feed['source']
                })
        except:
            pass
    now_hour = (datetime.utcnow().hour + 3) % 24
    header = '🌅 *Добрий ранок!*' if now_hour < 12 else '📰 *Свіжі новини:*'
    text = f'{header}\n\n'
    for i, it in enumerate(items[:5], 1):
        text += f"{i}. *{it['title']}*\n   {it['source']}\n   [Читати]({it['link']})\n\n"
    await bot.send_message(chat_id, text, parse_mode='Markdown', disable_web_page_preview=True)

async def morning_news(context):
    await fetch_news(context.bot, CHAT_ID)

# ── Тривоги ──────────────────────────────────────────────
async def check_alert(context):
    global alert_active
    if not ALERTS_KEY or ALERTS_KEY == 'empty':
        return
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                'https://api.alerts.in.ua/v1/alerts/active.json',
                headers={'X-API-Key': ALERTS_KEY}, timeout=10
            )
        lviv = any('львів' in str(a.get('location_title', '')).lower()
                   for a in r.json().get('alerts', []))
        if lviv and not alert_active:
            alert_active = True
            await context.bot.send_message(CHAT_ID,
                '🚨🚨🚨 *ТРИВОГА У ЛЬВОВІ!*\n\n🛡️ Негайно в укриття!',
                parse_mode='Markdown')
        elif not lviv and alert_active:
            alert_active = False
            await context.bot.send_message(CHAT_ID,
                '✅ *Відбій тривоги у Львові*', parse_mode='Markdown')
    except Exception as e:
        logger.error(f'Alert error: {e}')

# ── Нагадування ──────────────────────────────────────────
async def remind(context):
    rid = context.job.data['id']
    if rid not in reminders or not reminders[rid]['active']:
        context.job.schedule_removal()
        return
    kb = [[InlineKeyboardButton('✅ Готово!', callback_data=f'done_{rid}')]]
    await context.bot.send_message(CHAT_ID,
        f"⏰ *Нагадування:*\n_{reminders[rid]['text']}_",
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

def parse_time(text):
    t = text.lower()
    m = re.search(r'через\s+(\d+)\s+хвилин', t)
    if m:
        secs = int(m.group(1)) * 60
        note = re.sub(r'нагадай\s+мені\s+через\s+\d+\s+хвилин\s*', '', t).strip()
        return secs, note or t, f'через {m.group(1)} хвилин'
    m = re.search(r'через\s+(\d+)\s+год', t)
    if m:
        secs = int(m.group(1)) * 3600
        note = re.sub(r'нагадай\s+мені\s+через\s+\d+\s+год\w*\s*', '', t).strip()
        return secs, note or t, f'через {m.group(1)} годин'
    m = re.search(r'о\s+(\d{1,2}):(\d{2})', t)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        now = datetime.utcnow() + timedelta(hours=3)
        target = now.replace(hour=h, minute=mn, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        secs = int((target - now).total_seconds())
        note = re.sub(r'нагадай\s+мені\s+о\s+\d{1,2}:\d{2}\s*', '', t).strip()
        return secs, note or t, f'о {h:02d}:{mn:02d}'
    return None, None, None

# ── Команди ──────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '👋 *Привіт! Я твій особистий бот.*\n\n'
        '📰 Напиши *новини* — отримай свіжі новини\n'
        '⏰ Напиши *нагадай мені о 15:00 купити хліб*\n'
        '⏰ Напиши *нагадай мені через 30 хвилин зателефонувати*\n'
        '📝 Будь-який інший текст — повторне нагадування кожні 30 хв\n'
        '🚨 Слідкую за тривогами у Львові 24/7\n'
        '🌅 О 6:00 надсилаю ранкові новини автоматично',
        parse_mode='Markdown')

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    tl   = text.lower()

    # Новини
    if tl.startswith('новини'):
        await update.message.reply_text('⏳ Шукаю новини...')
        await fetch_news(context.bot, update.effective_chat.id)
        return

    # Нагадування з часом
    if 'нагадай' in tl:
        secs, note, time_str = parse_time(text)
        if secs:
            rid = str(len(reminders) + 1)
            reminders[rid] = {'text': note, 'active': True}
            kb = [[InlineKeyboardButton('✅ Готово!', callback_data=f'done_{rid}')]]
            await update.message.reply_text(
                f'⏰ *Нагадаю {time_str}:*\n_{note}_',
                parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
            context.job_queue.run_once(remind, when=secs,
                data={'id': rid}, name=f'r_{rid}')
        else:
            await update.message.reply_text(
                '❓ Не зрозумів час. Спробуй:\n'
                '• *нагадай мені о 15:00 купити хліб*\n'
                '• *нагадай мені через 30 хвилин зателефонувати*',
                parse_mode='Markdown')
        return

    # Звичайне повторне нагадування
    rid = str(len(reminders) + 1)
    reminders[rid] = {'text': text, 'active': True}
    kb = [[InlineKeyboardButton('✅ Готово!', callback_data=f'done_{rid}')]]
    await update.message.reply_text(
        f'📝 *Нагадування додано!*\n_{text}_\n\nНагадую кожні 30 хв 🔔',
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    context.job_queue.run_repeating(remind, interval=1800, first=1800,
        data={'id': rid}, name=f'r_{rid}')

async def on_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith('done_'):
        rid = q.data[5:]
        if rid in reminders:
            reminders[rid]['active'] = False
            for j in context.job_queue.get_jobs_by_name(f'r_{rid}'):
                j.schedule_removal()
            await q.edit_message_text(
                f"✅ *Виконано!*\n_{reminders[rid]['text']}_",
                parse_mode='Markdown')

# ── Запуск ───────────────────────────────────────────────
def main():
    threading.Thread(target=web, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CallbackQueryHandler(on_btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.job_queue.run_repeating(check_alert, interval=60, first=5)
    app.job_queue.run_daily(morning_news, time=time(3, 0))
    logger.info('✅ Bot started!')
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
