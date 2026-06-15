import asyncio
import logging
import os
from datetime import time

import httpx
import feedparser
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN    = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID  = int(os.getenv('TELEGRAM_CHAT_ID', '0'))
ALERTS_KEY = os.getenv('ALERTS_API_KEY', '')

reminders    = {}
alert_active = False

RSS_FEEDS = [
    {'url': 'https://kyivindependent.com/feed',              'source': 'Kyiv Independent 🇺🇦'},
    {'url': 'https://www.ukrinform.net/rss/block-lastnews',  'source': 'Ukrinform 🇺🇦'},
    {'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',    'source': 'BBC World 🌍'},
]

# ── Веб-сервер (щоб Render не засипав) ──────────────────
async def health(request):
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.router.add_get('/', health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
    await site.start()
    logger.info("Web server started")

# ── Тривоги Львів ────────────────────────────────────────
async def check_alert(context):
    global alert_active
    if not ALERTS_KEY:
        return
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.alerts.in.ua/v1/alerts/active.json",
                headers={"X-API-Key": ALERTS_KEY},
                timeout=10
            )
        alerts = r.json().get('alerts', [])
        lviv = any(
            'львів' in str(a.get('location_title', '')).lower()
            for a in alerts
        )
        if lviv and not alert_active:
            alert_active = True
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    "🚨🚨🚨 *ПОВІТРЯНА ТРИВОГА У ЛЬВОВІ!*\n\n"
                    "⚠️ Загроза ракети або шахеда!\n"
                    "🛡️ *Негайно в укриття!*"
                ),
                parse_mode='Markdown'
            )
        elif not lviv and alert_active:
            alert_active = False
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text="✅ *Відбій тривоги у Львові*\nМожна виходити з укриття.",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Alert error: {e}")

# ── Ранкові новини ───────────────────────────────────────
async def morning_news(context):
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

    text = "🌅 *Добрий ранок!*\n\n📰 *Топ новин за ніч:*\n\n"
    for i, it in enumerate(items[:5], 1):
        text += f"{i}. *{it['title']}*\n   {it['source']}\n   [Читати]({it['link']})\n\n"

    await context.bot.send_message(
        chat_id=CHAT_ID, text=text,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

# ── Нагадування ──────────────────────────────────────────
async def remind(context):
    rid = context.job.data['id']
    if rid not in reminders or not reminders[rid]['active']:
        context.job.schedule_removal()
        return
    keyboard = [[InlineKeyboardButton("✅ Готово!", callback_data=f"done_{rid}")]]
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=f"⏰ *Нагадування:*\n_{reminders[rid]['text']}_",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── Команди ──────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Привіт! Я твій особистий бот.*\n\n"
        "🚨 Слідкую за тривогами у Львові 24/7\n"
        "🌅 О 6:00 надсилаю ранкові новини\n"
        "📝 Напиши що треба зробити — нагадую поки не натиснеш *Готово*\n\n"
        "_Спробуй написати: Подзвонити мамі_",
        parse_mode='Markdown'
    )

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    rid  = str(len(reminders) + 1)
    reminders[rid] = {'text': text, 'active': True}

    keyboard = [[InlineKeyboardButton("✅ Готово!", callback_data=f"done_{rid}")]]
    await update.message.reply_text(
        f"📝 *Нагадування додано!*\n_{text}_\n\nБуду нагадувати кожні 30 хвилин 🔔",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.job_queue.run_repeating(
        remind, interval=1800, first=1800,
        data={'id': rid}, name=f"r_{rid}"
    )

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("done_"):
        rid = q.data[5:]
        if rid in reminders:
            reminders[rid]['active'] = False
            for job in context.job_queue.get_jobs_by_name(f"r_{rid}"):
                job.schedule_removal()
            await q.edit_message_text(
                f"✅ *Виконано!*\n_{reminders[rid]['text']}_",
                parse_mode='Markdown'
            )

# ── Запуск ───────────────────────────────────────────────
async def post_init(app):
    await run_web()

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    jq = app.job_queue
    jq.run_repeating(check_alert, interval=60, first=5)
    jq.run_daily(morning_news, time=time(3, 0))

    logger.info("✅ Бот запущено!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
