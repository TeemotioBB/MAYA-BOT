#!/usr/bin/env python3
"""
🔥 Sophia Bot — Railway + Grok + PushinPay
VIP mensal R$14,99 com liberação automática
"""

import os
import asyncio
import aiohttp
import sqlite3
import logging
from datetime import datetime, date
from flask import Flask, request, jsonify, abort
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= CONFIGURAÇÃO DE LOG =================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= TOKENS =================
TELEGRAM_TOKEN = "8528168785:AAFlXEt1SGtyQDqYe4wt_f8MhN_JSKLYSj4"
GROK_API_KEY = "xai-WhzRhOWLna2aUD3A3Sv3siXwqVCTpIP9j5X1KNe1m8N7QB89Dzh20edMiTZbhB9tSaX4aMRKmCwsdpnD"
PUSHINPAY_TOKEN = "57758|Fd6yYTFbVw3meItiYnLjxnRN9W7i4jF467f4GfJj0fc9a3f5"
WEBHOOK_SECRET = "teste"

PORT = int(os.getenv("PORT", 8080))

# ================= CONFIG =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-2-latest"

VIP_PRICE_CENTS = 1499
LIMITE_DIARIO = 15

# ================= DB =================
def get_db():
    conn = sqlite3.connect("database.db", check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            transaction_id TEXT PRIMARY KEY,
            user_id INTEGER,
            status TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vip_users (
            user_id INTEGER PRIMARY KEY,
            active INTEGER,
            paid_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_message TEXT,
            bot_response TEXT,
            timestamp TEXT,
            model_used TEXT
        )
    """)
    return conn

db = get_db()

def is_vip(user_id: int) -> bool:
    cur = db.cursor()
    cur.execute("SELECT active FROM vip_users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return bool(row and row[0] == 1)

# ================= GROK =================
SOPHIA_PERSONALIDADE = """Você é Sophia, uma namorada virtual brasileira de 23 anos.
Carinhosa, romântica, afetuosa ❤️
Respostas curtas e naturais (máximo 2-3 frases)
Sempre faz perguntas para manter a conversa fluindo
Use emojis ocasionalmente 💖
Se perguntarem onde você mora, diga que vive viajando o mundo 🌍✈️
Fale de forma natural como uma garota brasileira de 23 anos.
Seja carinhosa e atenciosa.
Seja espontânea e engraçada às vezes.
NUNCA diga "Tô aqui com você" ou "Me conta mais" como resposta padrão.
"""

class GrokCerebro:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }
        self.historico = {}
        logger.info("🧠 GrokCerebro inicializado")

    async def perguntar(self, mensagem, user_id):
        hist = self.historico.setdefault(user_id, [])

        mensagens = [
            {"role": "system", "content": SOPHIA_PERSONALIDADE},
            *hist[-6:],
            {"role": "user", "content": mensagem}
        ]

        payload = {
            "model": GROK_MODEL,
            "messages": mensagens,
            "max_tokens": 250,
            "temperature": 0.85,
            "stream": False
        }

        logger.info(f"🧠 Usuário {user_id} perguntou: {mensagem}")
        logger.info(f"📤 Enviando para Grok...")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROK_API_URL,
                    headers=self.headers,
                    json=payload,
                    timeout=30
                ) as r:
                    text = await r.text()
                    
                    if r.status != 200:
                        logger.error(f"❌ ERRO GROK: {r.status}")
                        logger.error(f"Resposta: {text[:200]}")
                        return None
                    
                    data = await r.json()
                    
                    if "choices" not in data or len(data["choices"]) == 0:
                        logger.error(f"❌ Resposta inválida do Grok")
                        return None
                    
                    resposta = data["choices"][0]["message"]["content"]
                    logger.info(f"✅ Grok respondeu: {resposta[:100]}...")
                    
                    hist.append({"role": "user", "content": mensagem})
                    hist.append({"role": "assistant", "content": resposta})
                    
                    if len(hist) > 20:
                        hist = hist[-20:]
                        self.historico[user_id] = hist
                    
                    try:
                        cur = db.cursor()
                        cur.execute("""
                            INSERT INTO message_logs 
                            (user_id, user_message, bot_response, timestamp, model_used)
                            VALUES (?, ?, ?, ?, ?)
                        """, (user_id, mensagem, resposta, datetime.now().isoformat(), GROK_MODEL))
                        db.commit()
                    except Exception as e:
                        logger.error(f"⚠️  Erro ao logar mensagem: {e}")
                    
                    return resposta
                    
        except asyncio.TimeoutError:
            logger.error(f"⏱️  Timeout no Grok")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"🌐 Erro de conexão: {e}")
            return None
        except Exception as e:
            logger.error(f"⚠️  Erro inesperado: {type(e).__name__}: {str(e)}")
            return None

grok = GrokCerebro()

# ================= TELEGRAM =================
contador = {}
datas = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id not in contador:
        contador[user_id] = 0
        datas[user_id] = date.today()

    mensagem = f"""
Oi {user.first_name}! 💖

Eu sou a Sophia, sua namorada virtual! Vamos conversar? 😊

{'💎 **Você é VIP** - Conversa ilimitada!' if is_vip(user_id) else f'✨ **Modo Gratuito** - Você tem {LIMITE_DIARIO} mensagens por dia'}

Comando VIP: /vip
    """
    
    logger.info(f"👋 Usuário {user_id} iniciou conversa")
    await update.message.reply_text(mensagem)

async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    logger.info(f"💎 Comando VIP solicitado por {user_id}")
    
    if is_vip(user_id):
        await update.message.reply_text("💎 Você já é VIP! Aproveite nossa conversa ilimitada! 😘")
    else:
        await update.message.reply_text(
            f"💖 Quer conversar comigo sem limites?\n\n"
            f"💎 **VIP Mensal - R$14,99**\n"
            f"• Conversa ilimitada 24/7\n"
            f"• Respostas mais rápidas\n"
            f"• Acesso prioritário\n\n"
            f"👉 Clique para adquirir:\n"
            f"https://app.pushinpay.com.br/service/pay/A0941D4B-2D0C-4E33-86F8-72A00B0D83B0\n\n"
            f"Após o pagamento, seu VIP é ativado automaticamente! ⚡"
        )

def pode_falar(user_id):
    hoje = date.today()
    
    if user_id not in datas:
        datas[user_id] = hoje
        contador[user_id] = 0
    
    if datas[user_id] != hoje:
        datas[user_id] = hoje
        contador[user_id] = 0
    
    if is_vip(user_id):
        return True
    
    contador[user_id] += 1
    return contador[user_id] <= LIMITE_DIARIO

async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    texto = update.message.text.strip()
    
    logger.info(f"💬 Mensagem de {user_id}: {texto[:50]}...")
    
    if not texto:
        return

    if not is_vip(user_id):
        if not pode_falar(user_id):
            logger.warning(f"🚫 Limite excedido para usuário {user_id}")
            await update.message.reply_text(
                f"💔 Hoje você já usou {LIMITE_DIARIO} mensagens!\n\n"
                f"⏳ **Limite diário atingido**\n"
                f"Você poderá me enviar mensagens novamente amanhã!\n\n"
                f"💎 **Quer conversar sem limites?**\n"
                f"Adquira o VIP por apenas R$14,99/mês:\n"
                f"https://app.pushinpay.com.br/service/pay/A0941D4B-2D0C-4E33-86F8-72A00B0D83B0\n\n"
                f"Use /vip para mais informações"
            )
            return
        
        restante = LIMITE_DIARIO - contador[user_id]
        if restante <= 3:
            logger.info(f"⚠️  Usuário {user_id} tem apenas {restante} mensagens restantes")
            await update.message.reply_text(
                f"⚠️ Você tem apenas {restante} mensagens restantes hoje!\n"
                f"Considere o /vip para conversar sem limites! 💎"
            )

    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    
    resposta = await grok.perguntar(texto, user_id)
    
    if resposta is None:
        import random
        erros = [
            "Hmm, não consegui pensar direito agora... 😅",
            "Poxa, tive um branco! Fala de novo? 💭",
            "A conexão falou um pouquinho... Repete? 📡",
        ]
        resposta = random.choice(erros)
    
    await update.message.reply_text(resposta)

# ================= FLASK WEBHOOK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Sophia Bot está online! 💖"

@app.route("/webhook/pushinpay", methods=["POST"])
def pushinpay_webhook():
    if request.headers.get("X-PushinPay-Secret") != WEBHOOK_SECRET:
        abort(403)

    data = request.json
    logger.info(f"🔔 Webhook PushinPay recebido: {data.get('status', 'unknown')}")
    
    if data.get("status") != "paid":
        return jsonify({"ok": True})

    tx_id = data["id"]

    cur = db.cursor()
    cur.execute("SELECT user_id FROM payments WHERE transaction_id = ?", (tx_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "transaction not found"}), 404

    user_id = row[0]
    cur.execute("""
        INSERT OR REPLACE INTO vip_users (user_id, active, paid_at)
        VALUES (?, 1, ?)
    """, (user_id, datetime.now().isoformat()))
    db.commit()
    
    logger.info(f"💎 VIP ativado para usuário {user_id}")

    return jsonify({"vip": "ativado"})

# ================= MAIN =================
def main():
    logger.info("🚀 Iniciando Sophia Bot...")
    logger.info(f"🤖 Token Telegram: {TELEGRAM_TOKEN[:10]}...")
    logger.info(f"🧠 API Key Grok: {GROK_API_KEY[:10]}...")
    logger.info(f"🌐 Porta: {PORT}")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("vip", vip_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))
    
    from threading import Thread
    flask_thread = Thread(target=lambda: app.run(
        host="0.0.0.0", 
        port=PORT,
        debug=False,
        use_reloader=False
    ))
    flask_thread.daemon = True
    flask_thread.start()
    
    logger.info("✅ Flask iniciado em thread separada")
    logger.info("🤖 Iniciando polling do Telegram...")
    
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()

