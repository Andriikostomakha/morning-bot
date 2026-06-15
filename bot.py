import logging
import os
import threading
from datetime import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import feedparser
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN      = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID    = int(os.getenv('TELEGRAM_CHAT_ID', '0'))
ALERTS_KEY = os.getenv('ALERTS_API_KEY', '')
reminders  = {}
alert_on   = False

RSS = [
    {'url': 'https://kyivindependent.com/feed',             'src': 'Kyiv Independent 🇺🇦'},
    {'url': 'https://www.ukrinform.net/rss/block-lastnews', 'src': 'Ukrinform 🇺🇦'},
    {'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',   'src': 'BBC World 🌍'},
]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, *a):
        pass

def web():
    port = int(os.getenv('PORT', 8080))
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()

async def check_alert(ctx):
    global alert_on
    if not ALERTS_KEY or ALERTS_KEY == 'empty':
        return
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                'https://api.alerts.in.ua/v1/alerts/active.json',
                headers={'X-API-Key': ALERTS_KEY}, timeout=10
            )
        lviv = any('львів' in str(a.get('location_title','')).lower() for a in r.json().get('alerts',[]))
        if lviv and not alert_on:
            alert_on = True
            await ctx.bot.send_message(CHAT_ID,
                '🚨🚨🚨 *ТРИВОГА У ЛЬВОВІ!*\n\n🛡️ Негайно в укриття!',
                parse_mode='Markdown')
        elif not lviv and alert_on:
            alert_on = False
            await ctx.bot.send_message(CHAT_ID,
                '✅ *Відбій тривоги у Львові*', parse_mode='Markdown')
    except Exception as e:
        logger.error(e)

async def news(ctx):
    items = []
    for f in RSS:
        try:
            for e in feedparser.parse(f['url']).entries[:2]:
                items.append({'t': e.get('title',''), 'l': e.get('link',''), 's': f['src']})
        except:
            pass
    text = '🌅 *Добрий ранок!*\n\n📰 *Новини за ніч:*\n\n'
    for i, it in enumerate(items[:5], 1):
        text += f"{i}. *{it['t']}*\n   {it['s']}\n   [Читати]({it['l']})\n\n"
    await ctx.bot.send_message(CHAT_ID, text, parse_mode='Markdown', disable_web_page_preview=True)

async def remind(ctx):
    rid = ctx.job.data['id']
    if rid not in reminders or not reminders[rid]['on']:
        ctx.job.schedule_removal()
        return
    kb = [[InlineKeyboardButton('✅ Готово!', callback_data=f'done_{rid}')]]
    await ctx.bot.send_message(CHAT_ID,
        f"⏰ *Нагадування:*\n_{reminders[rid]['text']}_",
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '👋 *Привіт! Я твій особистий бот.*\n\n'
        '🚨 Слідкую за тривогами у Львові 24/7\n'
        '🌅 О 6:00 надсилаю ранкові новини\n'
        '📝 Напиши що треба зробити — нагадую поки не натиснеш *Готово*',
        parse_mode='Markdown')

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    rid  = str(len(reminders) + 1)
    reminders[rid] = {'text': text, 'on': True}
    kb = [[InlineKeyboardButton('✅ Готово!', callback_data=f'done_{rid}')]]
    await update.message.reply_text(
        f'📝 *Додано!*\n_{text}_\n\nНагадую кожні 30 хв 🔔',
        parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    ctx.job_queue.run_repeating(remind, interval=1800, first=1800,
        data={'id': rid}, name=f'r_{rid}')

async def on_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith('done_'):
        rid = q.data[5:]
        if rid in reminders:
            reminders[rid]['on'] = False
            for j in ctx.job_queue.get_jobs_by_name(f'r_{rid}'):
                j.schedule_removal()
            await
