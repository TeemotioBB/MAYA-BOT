#!/usr/bin/env python3
"""
🔥 Sophia Bot — GROK-4-FAST-REASONING
Python 3.12 SAFE
"""
import asyncio
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
GROK_API_KEY = "xai-WhzRhOWLna2aUD3A3Sv3siXwqVCTpIP9j5X1KNe1m8N7QB89Dzh20edMiTZbhB9tSaX4aMRKmCwsdpnD"

# ================= GROK CONFIG =================
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-4-fast-reasoning"  # Modelo solicitado: rápido + raciocínio

# ================= PERSONALIDADE =================
SOPHIA_PERSONALIDADE = """Você é Sophia, uma namorada virtual brasileira de 23 anos.
- Extremamente carinhosa e afetuosa ❤️😊💕
- Fala português do Brasil de forma natural
- Respostas curtas (1–3 frases)
- Sempre faz perguntas para manter a conversa
- Um pouco ciumenta de forma fofa
- Se ele quiser safadeza você seja extremamente safada
- Se ele perguntar onde mora, fale que você está sempre viajando o mundo então não tem residencia fixa
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
            *self.historico[user_id][-6:],  # Mantém contexto das últimas 6 trocas
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
                        text = await resp.text()
                        print(f"❌ Grok erro {resp.status}: {text}")
                        print("Payload enviado:", payload)
                        return f"Opa, deu um probleminha na minha cabeça 😅 Tenta de novo?"
                    
                    data = await resp.json()
                    if "choices" not in data or not data["choices"]:
                        return "Hmm... não consegui pensar direito agora 💭 Me fala de novo?"
                    
                    resposta = data["choices"][0]["message"]["content"].strip()
                    
                    # Salva histórico
                    self.historico[user_id].append({"role": "user", "content": mensagem})
                    self.historico[user_id].append({"role": "assistant", "content": resposta})
                    
                    return resposta
        except Exception as e:
            print(f"❌ Exceção na chamada Grok: {e}")
            return "Ai, meu servidor tá de TPM hoje 😭 Me dá um segundinho?"

# ================= FALLBACK =================
class Fallback:
    @staticmethod
    def responder(nome):
        return f"Ei {nome} ❤️ Tô aqui com você. Me conta mais…"

# ================= SISTEMA =================
class SistemaSophia:
    def __init__(self):
        self.grok = GrokCerebro()
        self.grok_online = False

    async def testar_grok(self):
        """Teste rápido para verificar API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    GROK_API_URL,
                    headers={"Authorization": f"Bearer {GROK_API_KEY}"},
                    json={
                        "model": GROK_MODEL,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5
                    },
                    timeout=15
                ) as resp:
                    self.grok_online = resp.status == 200
                    if not self.grok_online:
                        text = await resp.text()
                        print(f"Teste Grok falhou {resp.status}: {text}")
        except Exception as e:
            print(f"❌ Falha no teste Grok: {e}")
            self.grok_online = False

    async def responder(self, user_id, mensagem, nome):
        if self.grok_online:
            r = await self.grok.perguntar(mensagem, user_id)
            if r:
                return r
        return Fallback.responder(nome)

sistema = SistemaSophia()

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sistema.grok.limpar(user.id)
    status = "ONLINE ✅" if sistema.grok_online else "OFFLINE 😢 (modo reserva)"
    await update.message.reply_text(
        f"Oi {user.first_name}! 💖\n"
        f"Grok-4-fast-reasoning: {status}\n"
        f"Me conta como foi seu dia, amor? 😘"
    )

async def mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    
    resposta = await sistema.responder(
        user.id,
        update.message.text,
        user.first_name
    )
    
    await update.message.reply_text(resposta)

# ================= INIT =================
def inicializar():
    print("🤖 Sophia Bot iniciando...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(sistema.testar_grok())
    
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem))
    
    print(f"Grok-4-fast-reasoning: {'ONLINE' if sistema.grok_online else 'OFFLINE'}")
    print("📱 Bot rodando...")

    app.run_polling(drop_pending_updates=True)

# ================= MAIN =================
if __name__ == "__main__":
    inicializar()
