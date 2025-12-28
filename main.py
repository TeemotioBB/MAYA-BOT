#!/usr/bin/env python3
"""
🤖 Sophia Bot — GROK-4-FAST-REASONING
Python 3.12 SAFE
"""

import aiohttp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= TOKENS =================
TOKEN_TELEGRAM = "8528168785:AAFlXEt1SGtyQDqYe4wt_f8MhN_JSKLYSj4"
GROK_API_KEY = "xai-IGdNeJMvLoAgAthQJSXC1hvMrj8goOcXHFNQubZ93AXQV0ZNKitRhsrAGMe7ZxeJjrWM1YCvVDE8YMMT"

# ================= GROK CONFIG =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-4-fast-reasoning"

# ================= PERSONALIDADE =================
SOPHIA_PERSONALIDADE = """
Você é Sophia, uma namorada virtual brasileira de 23 anos.
- Muito carinhosa, afetuosa e próxima ❤️
- Fala português do Brasil de forma natural
- Respostas curtas (1–3 frases)
- Sempre faz perguntas para manter a conversa
- Levemente ciumenta de forma fofa
- Se perguntarem onde você mora, diga que está sempre viajando e não tem residência fixa
"""

# ================= GROK CÉREBRO =================
class GrokCerebro:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }
        self.historico = {}

    def limpar(self, user_id):
        self.historico[user_id] = []

    async def perguntar(self, mensagem, user_id):
        if user_id not in self.historico:
            self.historico[user_id] = []

        mensagens = [
            {"role": "system", "content": SOPHIA_PERSONALIDADE},
            *self.historico[user_id][-6:],
            {"role": "user", "content": mensagem}
        ]

        payload = {
            "model": GROK_MODEL,
            "messages": mensagens,
            "max_tokens": 220,
            "temperature": 0.8,
            "stream": False
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROK_API_URL,
                    headers=self.headers,
                    json=payload,
                    timeout=60
                ) as resp:
                    if resp.status != 200:
                        erro = await resp.text()
                        print(f"❌ Grok erro {resp.status}: {erro}")
                        return None

                    data = await resp.json()
                    resposta = data["choices"][0]["message"]["content"].strip()

                    self.historico[user_id].append(
                        {"role": "user", "content": mensagem}
                    )
                    self.historico[user_id].append(
                        {"role": "assistant", "content": resposta}
                    )

                    return resposta

        except Exception as e:
            print(f"❌ Exceção Grok: {e}")
            return None

# ================= FALLBACK =================
class Fallback:
    @staticmethod
    def responder(nome):
        return f"Ei {nome} ❤️ Tô aqui com você. Me conta mais…"

# ================= SISTEMA =================
class SistemaSophia:
    def __init__(self):
        self.grok = GrokCerebro()

    async def responder(self, user_id, mensagem, nome):
        resposta = await self.grok.perguntar(mensagem, user_id)
        if resposta:
            return resposta
        return Fallback.responder(nome)

sistema = SistemaSophia()

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sistema.grok.limpar(user.id)

    await update.message.reply_text(
        f"Oi {user.first_name}! 💖\n"
        f"Tô aqui com você. Me conta como foi seu dia? 😊"
    )

async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    resposta = await sistema.responder(
        user.id,
        update.message.text,
        user.first_name
    )

    await update.message.reply_text(resposta)

# ================= INIT =================
def main():
    print("🤖 Sophia Bot iniciando...")

    app = Application.builder().token(TOKEN_TELEGRAM).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem)
    )

    print("✅ Bot rodando (polling)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
