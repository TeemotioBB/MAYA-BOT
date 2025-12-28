#!/usr/bin/env python3
"""
🔥 Sophia Bot — Railway + Grok + Telegram
"""

import os
import asyncio
import aiohttp
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.constants import ChatAction

# ================= LOG =================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= TOKENS =================
TELEGRAM_TOKEN = ("8528168785:AAFlXEt1SGtyQDqYe4wt_f8MhN_JSKLYSj4")
GROK_API_KEY = ("xai-IGdNeJMvLoAgAthQJSXC1hvMrj8goOcXHFNQubZ93AXQV0ZNKitRhsrAGMe7ZxeJjrWM1YCvVDE8YMMT")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "sophia123")
WEBHOOK_PATH = f"/telegram/{WEBHOOK_SECRET}"
PORT = int(os.getenv("PORT", 8080))

# Usar Railway URL automática
WEBHOOK_URL = os.getenv("RAILWAY_STATIC_URL", f"https://maya-bot-production.up.railway.app") + WEBHOOK_PATH

# ================= CONFIG =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-beta"  # Modelo mais estável

# ================= GROK =================
SOPHIA_PERSONALIDADE = """Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica e afetuosa ❤️
Respostas curtas e naturais (máx 2–3 frases)
Sempre faça perguntas
Use emojis ocasionalmente 💖"""

class GrokHandler:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }
        self.history = {}

    async def ask_grok(self, text: str, user_id: int) -> str:
        """Envia mensagem para Grok API"""
        
        # Pega histórico do usuário (mantém últimas 4 interações)
        user_history = self.history.get(user_id, [])
        messages = [{"role": "system", "content": SOPHIA_PERSONALIDADE}]
        
        # Adiciona histórico se existir
        for msg in user_history[-4:]:  # Mantém contexto curto
            messages.append(msg)
        
        messages.append({"role": "user", "content": text})
        
        payload = {
            "model": MODEL,
            "messages": messages,
            "max_tokens": 250,
            "temperature": 0.8
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROK_API_URL,
                    headers=self.headers,
                    json=payload,
                    timeout=20
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        reply = data["choices"][0]["message"]["content"]
                        
                        # Atualiza histórico
                        user_history.append({"role": "user", "content": text})
                        user_history.append({"role": "assistant", "content": reply})
                        self.history[user_id] = user_history[-6:]  # Limita histórico
                        
                        return reply
                    else:
                        error_text = await response.text()
                        logger.error(f"Grok API error {response.status}: {error_text}")
                        return "Desculpe, estou tendo problemas técnicos agora 😕"
                        
        except Exception as e:
            logger.error(f"Grok request failed: {e}")
            return "Hmm… não consegui processar sua mensagem. Pode repetir? 💖"

grok = GrokHandler()

# ================= TELEGRAM HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para comando /start"""
    user = update.effective_user
    welcome = f"Oi {user.first_name}! 💖\n\nSou a Sophia, sua namorada virtual.\nComo posso te fazer feliz hoje? 😘"
    await update.message.reply_text(welcome)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para todas as mensagens de texto"""
    user = update.effective_user
    text = update.message.text.strip()
    
    # Indica que está digitando
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )
    
    # Obtém resposta do Grok
    reply = await grok.ask_grok(text, user.id)
    
    # Envia resposta
    await update.message.reply_text(reply)

# ================= FLASK APP =================
app = Flask(__name__)

# Configura bot do Telegram
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.route("/")
def home():
    return "🤖 Sophia Bot está online!"

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    """Endpoint para webhook do Telegram"""
    update = Update.de_json(request.json, application.bot)
    application.create_task(application.process_update(update))
    return "ok", 200

# ================= MAIN =================
async def setup_webhook():
    """Configura webhook no Telegram"""
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook configurado: {WEBHOOK_URL}")

def main():
    """Função principal"""
    logger.info("🚀 Iniciando Sophia Bot...")
    
    # Configura webhook assincronamente
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())
    
    # Inicia servidor Flask
    app.run(host="0.0.0.0", port=PORT, debug=False)

if __name__ == "__main__":
    main()
