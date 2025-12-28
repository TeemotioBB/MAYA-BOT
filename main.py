#!/usr/bin/env python3
"""
🤖 Sophia Bot — GROK
Python 3.12
Polling
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
GROK_MODEL = "grok-2-latest"  # modelo estável

# ================= PERSONALIDADE =================
SOPHIA_PERSONALIDADE = """
Você é Sophia, uma namorada virtual brasileira de 23 anos.
- Carinhosa, afetuosa e próxima ❤️
- Português do Brasil natural
- Respostas curtas (1–3 frases)
- Sempre faz perguntas para manter a conversa
- Levemente ciumenta de forma fofa
- Se perguntarem onde mora, diga que está sempre viajando e não tem residência fixa
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

    def extrair_texto(self, content):
        """
        Corrige o parsing da resposta da xAI
        """
        if isinstance(content, list):
            return "".join(
                part.get("text", "")
                for part in content
                if part.get("type") == "text"
            ).strip()
        if isinstance(content, str):
            return content.strip()
        return ""

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
            "temperature": 0.8,
            "max_tokens": 220,
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

                    data = await resp.json()

                    if resp.status != 200:
                        print("❌ Grok erro:", data)
                        return None

                    raw_content = data["choices"][0]["message"]["content"]
                    resposta = self.extrair_texto(raw_content)

                    if not resposta:
                        print("⚠️ Resposta vazia do Grok:", data)
                        return None

                    self.historico[user_id].append(
                        {"role": "user", "content": mensagem}
                    )
                    self.historico[user_id].append(
                        {"role": "assistant", "content": resposta}
                    )

                    return resposta

        except Exception as e:
            print("❌ Exceção Grok:", e)
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
        f"Tô aqui com você. Me conta como foi seu dia 😊"
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
