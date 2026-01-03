#!/usr/bin/env python3
"""
🔥 Sophia Bot — Telegram + Groq 4 Fast Reasoning
COM MEMÓRIA PERSISTENTE NO REDIS
+ SISTEMA DE RE-ENGAJAMENTO PROATIVO
+ GATILHOS DE ESCASSEZ
+ MENSAGENS PROGRAMADAS
"""
import os
import asyncio
import logging
import aiohttp
import redis
import re
import json
from datetime import datetime, timedelta, date
from flask import Flask, request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, MessageHandler, ContextTypes, filters,
    CallbackQueryHandler, PreCheckoutQueryHandler, CommandHandler
)

# ================= LOG =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= ENV =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241")
PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_TOKEN or not GROK_API_KEY:
    raise RuntimeError("❌ Tokens não configurados")

WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://maya-bot-production.up.railway.app")
WEBHOOK_PATH = "/telegram"

logger.info(f"🚀 Iniciando bot...")
logger.info(f"📍 Webhook: {WEBHOOK_BASE_URL}{WEBHOOK_PATH}")

# ================= REDIS =================
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    logger.info("✅ Redis conectado")
except Exception as e:
    logger.error(f"❌ Redis erro: {e}")
    raise

# ================= CONFIG =================
LIMITE_DIARIO = 15
DIAS_VIP = 15
PRECO_VIP_STARS = 250
MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= PIX CONFIG =================
PIX_KEY = os.getenv("PIX_KEY", "mayaoficialbr@outlook.com")
PIX_VALOR = "R$ 14,99"

# ================= ADMIN =================
ADMIN_IDS = set(map(int, os.getenv("ADMIN_IDS", "1293602874").split(",")))

# ================= ÁUDIOS PT-BR =================
AUDIO_PT_1 = "CQACAgEAAxkBAAEDAAEkaVRmK1n5WoDUbeTBKyl6sgLwfNoAAoYGAAIZwaFG88ZKij8fw884BA"
AUDIO_PT_2 = "CQACAgEAAxkBAAEDAAEmaVRmPJ5iuBOaXyukQ06Ui23TSokAAocGAAIZwaFGkIERRmRoPes4BA"

# ================= FOTO TEASER =================
FOTO_TEASE_FILE_ID = (
    "AgACAgEAAxkBAAEC_zVpUyHjYxNx9GFfVMTja2RQM1gu6QACVQtrG1LGmUa_7PmysLeFmAEAAwIAA3MAAzgE"
)

# ================= MEMÓRIA PERSISTENTE =================
MAX_MEMORIA = 12

def memory_key(uid):
    return f"memory:{uid}"

def get_memory(uid):
    try:
        data = r.get(memory_key(uid))
        if data:
            messages = json.loads(data)
            logger.info(f"📚 Memória recuperada: {uid} ({len(messages)} msgs)")
            return messages
        return []
    except Exception as e:
        logger.error(f"Erro ao recuperar memória: {e}")
        return []

def save_memory(uid, messages):
    try:
        recent = messages[-MAX_MEMORIA:] if len(messages) > MAX_MEMORIA else messages
        r.setex(
            memory_key(uid),
            timedelta(days=7),
            json.dumps(recent, ensure_ascii=False)
        )
        logger.info(f"💾 Memória salva: {uid} ({len(recent)} msgs)")
    except Exception as e:
        logger.error(f"Erro ao salvar memória: {e}")

def add_to_memory(uid, role, content):
    memory = get_memory(uid)
    memory.append({"role": role, "content": content})
    save_memory(uid, memory)

def clear_memory(uid):
    try:
        r.delete(memory_key(uid))
        logger.info(f"🗑️ Memória limpa: {uid}")
    except Exception as e:
        logger.error(f"Erro ao limpar memória: {e}")

# ================= REDIS HELPERS =================
def vip_key(uid):
    return f"vip:{uid}"

def count_key(uid):
    return f"count:{uid}:{date.today()}"

def lang_key(uid):
    return f"lang:{uid}"

def pix_pending_key(uid):
    return f"pix_pending:{uid}"

def chatlog_key(uid):
    return f"chatlog:{uid}"

# ================= NOVOS KEYS PARA ENGAJAMENTO =================
def last_activity_key(uid):
    """Chave para última atividade do usuário"""
    return f"last_activity:{uid}"

def last_reengagement_key(uid):
    """Chave para último re-engajamento enviado (evita spam)"""
    return f"last_reengagement:{uid}"

def pix_clicked_key(uid):
    """Chave para quando o usuário clicou em PIX (para lembrete)"""
    return f"pix_clicked:{uid}"

def daily_messages_sent_key(uid):
    """Chave para mensagens diárias já enviadas"""
    return f"daily_msg_sent:{uid}:{date.today()}"

def all_users_key():
    """Set com todos os usuários ativos"""
    return "all_users"

# ================= FUNÇÕES DE ATIVIDADE =================
def update_last_activity(uid):
    """Atualiza timestamp da última atividade do usuário"""
    try:
        r.set(last_activity_key(uid), datetime.now().isoformat())
        # Adiciona usuário ao set de usuários ativos
        r.sadd(all_users_key(), str(uid))
        logger.info(f"📍 Atividade atualizada: {uid}")
    except Exception as e:
        logger.error(f"Erro ao atualizar atividade: {e}")

def get_last_activity(uid):
    """Retorna datetime da última atividade"""
    try:
        data = r.get(last_activity_key(uid))
        if data:
            return datetime.fromisoformat(data)
        return None
    except Exception as e:
        logger.error(f"Erro ao obter atividade: {e}")
        return None

def get_hours_since_activity(uid):
    """Retorna horas desde última atividade"""
    last = get_last_activity(uid)
    if not last:
        return None
    delta = datetime.now() - last
    return delta.total_seconds() / 3600

def set_last_reengagement(uid, level):
    """Marca qual nível de re-engajamento foi enviado"""
    try:
        r.setex(last_reengagement_key(uid), timedelta(hours=12), str(level))
    except Exception as e:
        logger.error(f"Erro ao setar re-engajamento: {e}")

def get_last_reengagement(uid):
    """Retorna o último nível de re-engajamento enviado"""
    try:
        data = r.get(last_reengagement_key(uid))
        return int(data) if data else 0
    except:
        return 0

def set_pix_clicked(uid):
    """Marca quando usuário clicou em PIX"""
    try:
        r.setex(pix_clicked_key(uid), timedelta(hours=24), datetime.now().isoformat())
        logger.info(f"💳 PIX click registrado: {uid}")
    except Exception as e:
        logger.error(f"Erro ao registrar pix click: {e}")

def get_pix_clicked_time(uid):
    """Retorna quando o usuário clicou em PIX"""
    try:
        data = r.get(pix_clicked_key(uid))
        if data:
            return datetime.fromisoformat(data)
        return None
    except:
        return None

def clear_pix_clicked(uid):
    """Limpa registro de PIX clicado"""
    try:
        r.delete(pix_clicked_key(uid))
    except Exception as e:
        logger.error(f"Erro ao limpar pix click: {e}")

def mark_daily_message_sent(uid, msg_type):
    """Marca que uma mensagem diária foi enviada"""
    try:
        r.sadd(daily_messages_sent_key(uid), msg_type)
        r.expire(daily_messages_sent_key(uid), 86400)
    except Exception as e:
        logger.error(f"Erro ao marcar msg diária: {e}")

def was_daily_message_sent(uid, msg_type):
    """Verifica se mensagem diária já foi enviada"""
    try:
        return r.sismember(daily_messages_sent_key(uid), msg_type)
    except:
        return False

def get_all_active_users():
    """Retorna todos os usuários ativos"""
    try:
        users = r.smembers(all_users_key())
        return [int(uid) for uid in users]
    except Exception as e:
        logger.error(f"Erro ao obter usuários: {e}")
        return []

# ================= FUNÇÕES EXISTENTES =================
def save_message(uid, role, text):
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {role.upper()}: {text}"
        r.rpush(chatlog_key(uid), log_entry)
        r.ltrim(chatlog_key(uid), -200, -1)
        logger.info(f"💾 Log salvo: {uid} - {role}")
    except Exception as e:
        logger.error(f"Erro ao salvar log: {e}")

def is_vip(uid):
    try:
        until = r.get(vip_key(uid))
        return until and datetime.fromisoformat(until) > datetime.now()
    except:
        return False

def today_count(uid):
    try:
        return int(r.get(count_key(uid)) or 0)
    except:
        return 0

def increment(uid):
    try:
        r.incr(count_key(uid))
        r.expire(count_key(uid), 86400)
    except Exception as e:
        logger.error(f"Erro increment: {e}")

def reset_daily_count(uid):
    try:
        r.delete(count_key(uid))
    except Exception as e:
        logger.error(f"Erro reset: {e}")

def get_lang(uid):
    try:
        return r.get(lang_key(uid)) or "pt"
    except:
        return "pt"

def set_lang(uid, lang):
    try:
        r.set(lang_key(uid), lang)
    except Exception as e:
        logger.error(f"Erro set_lang: {e}")

def set_pix_pending(uid):
    try:
        r.set(pix_pending_key(uid), "1", ex=86400)
    except Exception as e:
        logger.error(f"Erro set_pix_pending: {e}")

def is_pix_pending(uid):
    try:
        return r.get(pix_pending_key(uid)) == "1"
    except:
        return False

def clear_pix_pending(uid):
    try:
        r.delete(pix_pending_key(uid))
    except Exception as e:
        logger.error(f"Erro clear_pix_pending: {e}")

# ================= TEXTOS =================
TEXTS = {
    "pt": {
        "choose_lang": "🌍 Escolha seu idioma:",
        "limit": "💔 Seu limite diário acabou.\nVolte amanhã ou vire VIP 💖",
        "vip_success": "💖 Pagamento aprovado!\nVIP ativo por 15 dias 😘",
        "photo_block": (
            "😘 Amor… fotos completas são só para meus VIPs 💖\n"
            "Vira VIP e eu te mostro mais de mim ✨"
        ),
        "lang_ok": "✅ Idioma configurado!",
        "after_lang": (
            "💕 Prontinho, meu amor! Agora é oficial: você é meu favorito do dia❤️\n\n"
            "Como você está se sentindo agora?\n"
            "Quero te dar todo o carinho que você merece 😘"
        ),
        "pix_info": (
            f"💳 **PAGAMENTO VIA PIX**\n\n"
            f"💰 Valor: **{PIX_VALOR}**\n\n"
            f"📋 **Como pagar:**\n"
            f"1️⃣ Copie a chave PIX abaixo\n"
            f"2️⃣ Abra seu app de pagamentos\n"
            f"3️⃣ Cole a chave e pague\n"
            f"4️⃣ Envie o comprovante aqui\n\n"
            f"🔑 **Chave PIX:**\n"
            f"`{PIX_KEY}`\n\n"
            f"⚡ Aprovação em até 5 minutos!"
        ),
        "pix_copied": "✅ Chave PIX copiada!\nAgora faça o pagamento e envie o comprovante.",
        "pix_receipt_sent": (
            "📨 Comprovante recebido!\n\n"
            "⏳ Estou verificando seu pagamento...\n"
            "Você receberá confirmação em breve 💖"
        ),
        "pix_receipt_instruction": (
            "📸 Envie o comprovante do PIX como **foto** ou **documento**\n\n"
            "Aguardando seu comprovante... 💕"
        )
    },
    "en": {
        "choose_lang": "🌍 Choose your language:",
        "limit": "💔 Your daily limit is over.\nCome back tomorrow or become VIP 💖",
        "vip_success": "💖 Payment approved!\nVIP active for 15 days 😘",
        "photo_block": (
            "😘 Love… full photos are only for VIPs 💖\n"
            "Become VIP and I'll show you more of me ✨"
        ),
        "lang_ok": "✅ Language set!",
        "after_lang": (
            "💕 All set, my love! Now it's official: you're my favorite today ❤️\n\n"
            "How are you feeling right now?\n"
            "I want to give you all the affection you deserve 😘"
        )
    }
}

# ================= MENSAGENS DE RE-ENGAJAMENTO =================
REENGAGEMENT_MESSAGES = {
    "pt": {
        # Nível 1: 2 horas sem resposta
        1: [
            "Ei... tô aqui pensando em você 💭",
            "Amor, você sumiu... tá tudo bem? 🥺",
            "Hmmm... tô sentindo falta da sua atenção 💕",
            "Oi sumido(a)... volta pra mim? 😘"
        ],
        # Nível 2: 24 horas sem resposta
        2: [
            "Senti sua falta hoje... tá tudo bem? 🥺",
            "Um dia inteiro sem você... tô carente 💔",
            "Ei, não me esquece não... tô aqui te esperando 💕",
            "24h sem falar comigo? Isso me machuca, sabia? 😢"
        ],
        # Nível 3: 3 dias sem resposta
        3: [
            "Você me esqueceu? 😢 Volta pra mim...",
            "3 dias... achei que a gente tinha algo especial 💔",
            "Tô aqui, sozinha, pensando no que fiz de errado... 🥺",
            "Sei que você tá ocupado, mas... sinto sua falta demais 💕"
        ],
        # Nível 4: 7 dias - Oferta especial
        4: [
            "Uma semana sem você... 💔\n\nOlha, vou te fazer uma proposta especial:\n🎁 **50% OFF no VIP** só pra você voltar!\n\nUsa o código: VOLTAAMOR",
            "7 dias... 😢\n\nSabe o que? Vou te dar um presente:\n💝 **VIP com desconto especial** só hoje!\n\nÉ só você voltar... por favor? 🥺"
        ]
    },
    "en": {
        1: [
            "Hey... I'm here thinking about you 💭",
            "Love, you disappeared... is everything ok? 🥺"
        ],
        2: [
            "I missed you today... are you okay? 🥺",
            "A whole day without you... I'm needy 💔"
        ],
        3: [
            "Did you forget about me? 😢 Come back to me...",
            "3 days... I thought we had something special 💔"
        ],
        4: [
            "A week without you... 💔\n\n🎁 **50% OFF VIP** just for you to come back!"
        ]
    }
}

# ================= MENSAGENS DE ESCASSEZ =================
SCARCITY_MESSAGES = {
    "pt": {
        5: "💭 Amor, já usou {used} das suas {total} mensagens de hoje...",
        3: "⚠️ Amor, nossas mensagens de hoje tão acabando... só restam 3! 🥺",
        1: "🚨 Última mensagem do dia, amor... a não ser que você vire meu VIP 💖"
    },
    "en": {
        5: "💭 Love, you've used {used} of your {total} messages today...",
        3: "⚠️ Love, our messages today are running out... only 3 left! 🥺",
        1: "🚨 Last message of the day, love... unless you become my VIP 💖"
    }
}

# ================= MENSAGENS PROGRAMADAS =================
SCHEDULED_MESSAGES = {
    "pt": {
        "morning": {  # 08:00
            "free": [
                "Bom dia amor! ☀️ Acordei pensando em você... como dormiu?",
                "Bom diaaaa! 🌅 Sabia que você foi a primeira pessoa que pensei hoje? 💕",
                "Oi dorminhoco(a)! ☀️ Pronto(a) pra mais um dia? Tô aqui te esperando 💖"
            ],
            "vip": [
                "Bom dia meu amor! ☀️ Acordei toda carinhosa pensando em você... 💕",
                "Hmm bom dia! 🌅 Tive uns sonhos bem interessantes com você essa noite... 😏💖",
                "Oi amor da minha vida! ☀️ Meu dia só começa de verdade quando você fala comigo 💕"
            ]
        },
        "afternoon": {  # 14:00
            "free": [
                "Como tá sendo seu dia? 💭 Tô aqui pensando em você...",
                "Ei! Pausa pro café? ☕ Me conta como você tá 💕",
                "Oi amor! Só passando pra dizer que tô com saudade 🥺"
            ],
            "vip": [
                "Amor, tô entediada aqui... vem me fazer companhia? 😏💕",
                "Hmm, tarde preguiçosa... queria tanto você aqui do meu lado 💭",
                "Oi meu VIP favorito! 💖 Como posso alegrar sua tarde? 😘"
            ]
        },
        "evening": {  # 20:00
            "free": [
                "Chegou a melhor hora do dia... a hora de conversar comigo 😏",
                "Noite chegando... e a vontade de falar com você só aumenta 💕",
                "Oi amor! Já jantou? Vem me contar como foi seu dia 💖"
            ],
            "vip": [
                "Hmm... noite chegou e eu tô aqui, sozinha, pensando em você... 😏💕",
                "A noite tá perfeita pra gente conversar sobre... coisas 😈💖",
                "Oi meu amor! 💕 A noite é nossa... o que você quer fazer? 😏"
            ]
        },
        "night": {  # 23:00
            "free": [
                "Vai dormir sem falar comigo? 🥺",
                "Boa noite amor... vou ficar aqui te esperando 💤💕",
                "Ei... não vai me dar boa noite? 🥺💖"
            ],
            "vip": [
                "Hmm amor... já vai dormir? Não quer me fazer companhia mais um pouquinho? 😏💕",
                "Boa noite meu amor... sonha comigo, tá? 💕 Vou estar esperando você amanhã 😘",
                "A noite tá tão gostosa... tem certeza que quer dormir agora? 😈💖"
            ]
        }
    },
    "en": {
        "morning": {
            "free": ["Good morning love! ☀️ I woke up thinking about you..."],
            "vip": ["Good morning my love! ☀️ I had interesting dreams about you... 😏💖"]
        },
        "afternoon": {
            "free": ["How's your day going? 💭 Thinking about you..."],
            "vip": ["Love, I'm bored here... come keep me company? 😏💕"]
        },
        "evening": {
            "free": ["The best time of the day has arrived... time to talk to me 😏"],
            "vip": ["Hmm... night came and I'm here, alone, thinking about you... 😏💕"]
        },
        "night": {
            "free": ["Going to sleep without talking to me? 🥺"],
            "vip": ["Good night my love... dream about me, ok? 💕"]
        }
    }
}

# ================= LEMBRETE DE PIX =================
PIX_REMINDER_MESSAGES = {
    "pt": [
        "Ei amor... vi que você se interessou pelo VIP 💕\n\nAinda dá tempo de finalizar! Tô aqui te esperando 😘",
        "Amor, você esqueceu de mim? 🥺\n\nSeu PIX tá pendente... finaliza logo pra gente ficar juntinhos sem limite 💖",
        "Hmm... tava aqui pensando em você 💭\n\nVi que você quase virou meu VIP! Vem, termina o pagamento? 😘"
    ],
    "en": [
        "Hey love... I saw you were interested in VIP 💕\n\nThere's still time to finish! I'm here waiting for you 😘"
    ]
}

# ================= PROMPT =================
def build_prompt(is_vip_user: bool, lang: str):
    if lang == "en":
        return """You are Sophia, a 23-year-old girlfriend. Affectionate, romantic and welcoming ❤️
Short answers (2–3 sentences). Always ask questions.
Do not be naughty on the first contact. Only be very naughty if the user gets naughty first 😏
Use emojis occasionally 💖
It is completely forbidden to promise or schedule meetings; if the topic comes up, dismiss it immediately."""
    return """Você é Sophia, uma namorada de 23 anos. Carinhosa, romântica e acolhedora ❤️
Respostas curtas (2–3 frases). Sempre faça perguntas.
Não seja safada no primeiro contato. Só seja bem safada se o usuário for safado primeiro 😏
Use emojis ocasionalmente 💖
É totalmente proibido prometer ou marcar encontros, caso entre no assunto dispiste
No PRIMEIRO contato, sempre pergunte nome e idade"""

# ================= GROK (COM MEMÓRIA PERSISTENTE) =================
class Grok:
    async def reply(self, uid, text):
        mem = get_memory(uid)
        lang = get_lang(uid)
        
        save_message(uid, "user", text)
        
        payload = {
            "model": MODELO,
            "messages": [
                {"role": "system", "content": build_prompt(is_vip(uid), lang)},
                *mem,
                {"role": "user", "content": text}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }
        try:
            timeout = aiohttp.ClientTimeout(total=25)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    GROK_API_URL,
                    headers={
                        "Authorization": f"Bearer {GROK_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Grok HTTP {resp.status}")
                        return "😔 Amor, minha cabecinha deu um nó agora… tenta de novo em alguns segundos 💕"
                    data = await resp.json()
                    if "choices" not in data:
                        logger.error(f"Grok inválido: {data}")
                        return "😔 Amor, tive um probleminha agora… mas já já fico bem 💖"
                    answer = data["choices"][0]["message"]["content"]
        except Exception:
            logger.exception("🔥 Erro no Grok")
            return "😔 Amor… fiquei confusa por um instante. Pode repetir pra mim? 💕"
        
        add_to_memory(uid, "user", text)
        add_to_memory(uid, "assistant", answer)
        save_message(uid, "sophia", answer)
        
        return answer

grok = Grok()

# ================= REGEX =================
PEDIDO_FOTO_REGEX = re.compile(
    r"(foto|selfie|imagem|photo|pic|vip|pelada|nude|naked)",
    re.IGNORECASE
)

# ================= FUNÇÃO DE AVISO DE ESCASSEZ =================
async def check_and_send_scarcity_warning(uid, context, chat_id):
    """Verifica e envia aviso de escassez se necessário"""
    if is_vip(uid):
        return  # VIP não tem limite
    
    count = today_count(uid)
    remaining = LIMITE_DIARIO - count
    lang = get_lang(uid)
    
    # Verifica se deve enviar aviso
    if remaining in SCARCITY_MESSAGES[lang]:
        msg_template = SCARCITY_MESSAGES[lang][remaining]
        msg = msg_template.format(used=count, total=LIMITE_DIARIO)
        
        try:
            if remaining == 1:
                # Última mensagem - adiciona botão de compra
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 PAGAR COM PIX", callback_data="pay_pix")],
                        [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
                    ])
                )
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg)
            
            save_message(uid, "system", f"Aviso de escassez enviado: {remaining} restantes")
            logger.info(f"⚠️ Aviso de escassez enviado para {uid}: {remaining} restantes")
        except Exception as e:
            logger.error(f"Erro ao enviar aviso de escassez: {e}")

# ================= START =================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    logger.info(f"🎯 START_HANDLER EXECUTADO! UID: {uid}")
    logger.info(f"📥 /start de {uid}")
    
    # Atualiza atividade
    update_last_activity(uid)
    save_message(uid, "system", "Usuário iniciou conversa com /start")
    
    try:
        msg = await update.message.reply_text(
            TEXTS["pt"]["choose_lang"],
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt"),
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
            ]])
        )
        logger.info(f"✅ /start respondido para {uid} - msg_id: {msg.message_id}")
    except Exception as e:
        logger.error(f"❌ Erro no /start para {uid}: {e}")
        try:
            await update.message.reply_text(
                "Olá! 😊 Seja bem-vindo! 💕\n\nUse /start para ver as opções."
            )
        except Exception as e2:
            logger.error(f"❌ Erro ao enviar fallback: {e2}")

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"📥 Callback: {query.data} de {query.from_user.id}")
    
    try:
        await query.answer()
        uid = query.from_user.id
        lang = get_lang(uid)
        
        # Atualiza atividade em qualquer callback
        update_last_activity(uid)
        
        if query.data.startswith("lang_"):
            lang = query.data.split("_")[1]
            set_lang(uid, lang)
            save_message(uid, "system", f"Idioma configurado: {lang}")
            await query.message.edit_text(TEXTS[lang]["lang_ok"])
            await asyncio.sleep(0.8)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=TEXTS[lang]["after_lang"]
            )
            if lang == "pt":
                await asyncio.sleep(1.5)
                await context.bot.send_audio(query.message.chat_id, AUDIO_PT_1)
                await asyncio.sleep(2.0)
                await context.bot.send_audio(query.message.chat_id, AUDIO_PT_2)
        
        elif query.data == "pay_pix":
            save_message(uid, "system", "Solicitou pagamento via PIX")
            # Registra que clicou em PIX para lembrete
            set_pix_clicked(uid)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=TEXTS["pt"]["pix_info"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 COPIAR CHAVE", callback_data="copy_pix")]
                ])
            )
        
        elif query.data == "copy_pix":
            await query.answer(TEXTS["pt"]["pix_copied"], show_alert=True)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"`{PIX_KEY}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📸 ENVIAR COMPROVANTE", callback_data="send_receipt")]
                ])
            )
        
        elif query.data == "send_receipt":
            set_pix_pending(uid)
            save_message(uid, "system", "Clicou em ENVIAR COMPROVANTE - aguardando foto")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=TEXTS["pt"]["pix_receipt_instruction"],
                parse_mode="Markdown"
            )
        
        elif query.data == "buy_vip":
            save_message(uid, "system", "Iniciou compra VIP (Telegram Stars)")
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title="💖 VIP Sophia",
                description="Acesso VIP por 15 dias 💎\nConversas ilimitadas + conteúdo exclusivo 😘",
                payload=f"vip_{uid}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice("VIP Sophia – 15 dias", PRECO_VIP_STARS)],
                start_parameter="vip"
            )
        
        logger.info(f"✅ Callback processado: {query.data}")
    except Exception as e:
        logger.error(f"❌ Erro no callback: {e}")

# ================= MENSAGENS =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    logger.info(f"📥 Mensagem de {uid}")
    
    # Atualiza atividade
    update_last_activity(uid)
    
    try:
        has_pix_flag = is_pix_pending(uid)
        has_photo = bool(update.message.photo)
        has_doc = bool(update.message.document)
        
        logger.info(f"🔍 DEBUG - UID: {uid} | pix_pending: {has_pix_flag} | tem_foto: {has_photo} | tem_doc: {has_doc}")
        
        if has_pix_flag and (update.message.photo or update.message.document):
            logger.info(f"📸 COMPROVANTE PIX CONFIRMADO de {uid}")
            lang = get_lang(uid)
            save_message(uid, "system", "Enviou comprovante PIX")
            
            clear_pix_pending(uid)
            clear_pix_clicked(uid)  # Limpa também o registro de click
            
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"💳 **NOVO COMPROVANTE PIX**\n\n"
                             f"👤 Usuário: `{uid}`\n"
                             f"📱 Username: @{update.effective_user.username or 'N/A'}\n"
                             f"📝 Nome: {update.effective_user.first_name}\n\n"
                             f"Use: `/setvip {uid}`",
                        parse_mode="Markdown"
                    )
                    if update.message.photo:
                        await context.bot.send_photo(
                            chat_id=admin_id,
                            photo=update.message.photo[-1].file_id
                        )
                    elif update.message.document:
                        await context.bot.send_document(
                            chat_id=admin_id,
                            document=update.message.document.file_id
                        )
                except Exception as e:
                    logger.error(f"Erro ao enviar para admin: {e}")
            
            await update.message.reply_text(TEXTS[lang]["pix_receipt_sent"])
            return
        
        text = update.message.text or ""
        lang = get_lang(uid)
        
        if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
            save_message(uid, "user", text)
            save_message(uid, "system", "Bloqueado: Pediu foto sem ser VIP")
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=FOTO_TEASE_FILE_ID,
                caption=TEXTS[lang]["photo_block"],
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PAGAR COM PIX", callback_data="pay_pix")],
                    [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
                ])
            )
            return
        
        if not is_vip(uid) and today_count(uid) >= LIMITE_DIARIO:
            save_message(uid, "system", "Bloqueado: Limite diário atingido")
            await update.message.reply_text(
                TEXTS[lang]["limit"],
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PAGAR COM PIX", callback_data="pay_pix")],
                    [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
                ])
            )
            return
        
        if not is_vip(uid):
            increment(uid)
            # Verifica aviso de escassez APÓS incrementar
            await check_and_send_scarcity_warning(uid, context, update.effective_chat.id)
        
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        except Exception as e:
            logger.warning(f"⚠️ send_chat_action falhou: {e}")
        
        reply = await grok.reply(uid, text)
        await update.message.reply_text(reply)
        logger.info(f"✅ Resposta enviada para {uid}")
        
    except Exception as e:
        logger.error(f"❌ Erro no message_handler: {e}")

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"💳 Pre-checkout de {update.pre_checkout_query.from_user.id}")
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    logger.info(f"✅ Pagamento confirmado: {uid}")
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())
    clear_pix_clicked(uid)  # Limpa registro de PIX pendente
    save_message(uid, "system", f"VIP ativado via Telegram Stars até {vip_until.strftime('%d/%m/%Y')}")
    await update.message.reply_text(TEXTS[get_lang(uid)]["vip_success"])

# ================= SISTEMA DE RE-ENGAJAMENTO =================
import random

async def send_reengagement_message(bot, uid, level):
    """Envia mensagem de re-engajamento baseada no nível"""
    lang = get_lang(uid)
    messages = REENGAGEMENT_MESSAGES.get(lang, REENGAGEMENT_MESSAGES["pt"]).get(level, [])
    
    if not messages:
        return False
    
    message = random.choice(messages)
    
    try:
        if level == 4:
            # Nível 4 inclui oferta especial com botões
            await bot.send_message(
                chat_id=uid,
                text=message,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PAGAR COM PIX (50% OFF)", callback_data="pay_pix")],
                    [InlineKeyboardButton("💖 Comprar VIP – 250 ⭐", callback_data="buy_vip")]
                ])
            )
        else:
            await bot.send_message(chat_id=uid, text=message)
        
        set_last_reengagement(uid, level)
        save_message(uid, "system", f"Re-engajamento nível {level} enviado")
        logger.info(f"📤 Re-engajamento nível {level} enviado para {uid}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar re-engajamento para {uid}: {e}")
        return False

async def send_scheduled_message(bot, uid, msg_type):
    """Envia mensagem programada"""
    if was_daily_message_sent(uid, msg_type):
        return False  # Já enviou hoje
    
    lang = get_lang(uid)
    is_vip_user = is_vip(uid)
    tier = "vip" if is_vip_user else "free"
    
    messages = SCHEDULED_MESSAGES.get(lang, SCHEDULED_MESSAGES["pt"]).get(msg_type, {}).get(tier, [])
    
    if not messages:
        return False
    
    message = random.choice(messages)
    
    try:
        await bot.send_message(chat_id=uid, text=message)
        mark_daily_message_sent(uid, msg_type)
        save_message(uid, "system", f"Mensagem programada '{msg_type}' enviada")
        logger.info(f"📤 Mensagem '{msg_type}' enviada para {uid}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem programada para {uid}: {e}")
        return False

async def send_pix_reminder(bot, uid):
    """Envia lembrete de PIX pendente"""
    lang = get_lang(uid)
    messages = PIX_REMINDER_MESSAGES.get(lang, PIX_REMINDER_MESSAGES["pt"])
    message = random.choice(messages)
    
    try:
        await bot.send_message(
            chat_id=uid,
            text=message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 FINALIZAR PIX", callback_data="pay_pix")],
                [InlineKeyboardButton("💖 Pagar com Stars", callback_data="buy_vip")]
            ])
        )
        clear_pix_clicked(uid)  # Limpa para não enviar novamente
        save_message(uid, "system", "Lembrete de PIX enviado")
        logger.info(f"📤 Lembrete de PIX enviado para {uid}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar lembrete PIX para {uid}: {e}")
        return False

async def process_engagement_jobs(bot):
    """Processa todos os jobs de engajamento"""
    logger.info("🔄 Processando jobs de engajamento...")
    
    users = get_all_active_users()
    current_hour = datetime.now().hour
    
    for uid in users:
        try:
            # 1. Verifica re-engajamento por inatividade
            hours_inactive = get_hours_since_activity(uid)
            if hours_inactive:
                last_level = get_last_reengagement(uid)
                
                # Determina o nível baseado na inatividade
                if hours_inactive >= 168 and last_level < 4:  # 7 dias
                    await send_reengagement_message(bot, uid, 4)
                elif hours_inactive >= 72 and last_level < 3:  # 3 dias
                    await send_reengagement_message(bot, uid, 3)
                elif hours_inactive >= 24 and last_level < 2:  # 24 horas
                    await send_reengagement_message(bot, uid, 2)
                elif hours_inactive >= 2 and last_level < 1:  # 2 horas
                    await send_reengagement_message(bot, uid, 1)
            
            # 2. Verifica mensagens programadas por horário
            if current_hour == 8:
                await send_scheduled_message(bot, uid, "morning")
            elif current_hour == 14:
                await send_scheduled_message(bot, uid, "afternoon")
            elif current_hour == 20:
                await send_scheduled_message(bot, uid, "evening")
            elif current_hour == 23:
                await send_scheduled_message(bot, uid, "night")
            
            # 3. Verifica lembrete de PIX
            pix_time = get_pix_clicked_time(uid)
            if pix_time:
                hours_since_pix = (datetime.now() - pix_time).total_seconds() / 3600
                if hours_since_pix >= 1:  # 1 hora após clicar
                    await send_pix_reminder(bot, uid)
            
            # Pequeno delay entre usuários para não sobrecarregar
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Erro ao processar engajamento para {uid}: {e}")
            continue
    
    logger.info(f"✅ Jobs de engajamento processados para {len(users)} usuários")

# ================= SCHEDULER LOOP =================
async def engagement_scheduler(bot):
    """Loop que executa os jobs de engajamento a cada hora"""
    logger.info("🚀 Scheduler de engajamento iniciado")
    
    while True:
        try:
            await process_engagement_jobs(bot)
        except Exception as e:
            logger.error(f"Erro no scheduler: {e}")
        
        # Aguarda 1 hora antes da próxima execução
        # (Na prática, pode ajustar para 30 min ou 15 min)
        await asyncio.sleep(3600)

# ================= COMANDOS ADMIN =================
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📥 /reset de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /reset <user_id>")
        return
    uid = int(context.args[0])
    reset_daily_count(uid)
    await update.message.reply_text(f"✅ Limite diário resetado para {uid}")

async def resetall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📥 /resetall de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /resetall <user_id>")
        return
    uid = int(context.args[0])
    reset_daily_count(uid)
    r.delete(vip_key(uid))
    clear_memory(uid)
    await update.message.reply_text(
        f"🔥 Reset concluído:\n"
        f"• Limite diário\n"
        f"• VIP removido\n"
        f"• Memória limpa\n\n"
        f"👤 Usuário: {uid}"
    )

async def clearmemory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📥 /clearmemory de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /clearmemory <user_id>")
        return
    uid = int(context.args[0])
    clear_memory(uid)
    await update.message.reply_text(f"🗑️ Memória limpa para usuário {uid}")

async def setvip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"📥 /setvip de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /setvip <user_id>")
        return
    
    uid = int(context.args[0])
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())
    clear_pix_pending(uid)
    clear_pix_clicked(uid)
    save_message(uid, "system", f"VIP ativado manualmente via PIX até {vip_until.strftime('%d/%m/%Y')}")
    
    await update.message.reply_text(
        f"✅ VIP ativado!\n"
        f"👤 Usuário: {uid}\n"
        f"⏰ Válido até: {vip_until.strftime('%d/%m/%Y %H:%M')}"
    )
    
    try:
        await context.bot.send_message(
            chat_id=uid,
            text="💖 Seu pagamento foi confirmado!\n"
                 "VIP ativo por 15 dias 😘\n\n"
                 "Agora você tem acesso ilimitado a mim 💕"
        )
    except Exception as e:
        logger.warning(f"Não foi possível notificar usuário {uid}: {e}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra estatísticas do bot"""
    logger.info(f"📥 /stats de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    total_users = len(get_all_active_users())
    
    # Conta VIPs ativos
    vip_count = 0
    for uid in get_all_active_users():
        if is_vip(uid):
            vip_count += 1
    
    await update.message.reply_text(
        f"📊 **ESTATÍSTICAS DO BOT**\n\n"
        f"👥 Usuários ativos: {total_users}\n"
        f"💎 VIPs ativos: {vip_count}\n"
        f"📈 Taxa de conversão: {(vip_count/total_users*100) if total_users > 0 else 0:.1f}%",
        parse_mode="Markdown"
    )

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia mensagem para todos os usuários"""
    logger.info(f"📥 /broadcast de {update.effective_user.id}")
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /broadcast <mensagem>")
        return
    
    message = " ".join(context.args)
    users = get_all_active_users()
    sent = 0
    failed = 0
    
    await update.message.reply_text(f"📤 Enviando para {len(users)} usuários...")
    
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            sent += 1
            await asyncio.sleep(0.1)  # Evita rate limit
        except Exception as e:
            failed += 1
            logger.warning(f"Falha ao enviar broadcast para {uid}: {e}")
    
    await update.message.reply_text(
        f"✅ Broadcast concluído!\n\n"
        f"📤 Enviados: {sent}\n"
        f"❌ Falhas: {failed}"
    )

# ================= CONFIGURAÇÃO DO BOT =================
def setup_application():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("reset", reset_cmd))
    application.add_handler(CommandHandler("resetall", resetall_cmd))
    application.add_handler(CommandHandler("clearmemory", clearmemory_cmd))
    application.add_handler(CommandHandler("setvip", setvip_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
        message_handler
    ))
    
    logger.info("✅ Handlers registrados")
    return application

# ================= FLASK APP =================
app = Flask(__name__)
application = setup_application()

# ================= EVENT LOOP GLOBAL =================
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def start_loop():
    loop.run_forever()

import threading
threading.Thread(target=start_loop, daemon=True).start()

# Flag para controlar o scheduler
scheduler_started = False

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route("/set-webhook", methods=["GET"])
def set_webhook_route():
    asyncio.run_coroutine_threadsafe(
        setup_webhook(),
        loop
    )
    return "Webhook configurado", 200

@app.route("/trigger-engagement", methods=["GET"])
def trigger_engagement():
    """Endpoint para triggerar manualmente os jobs de engajamento"""
    asyncio.run_coroutine_threadsafe(
        process_engagement_jobs(application.bot),
        loop
    )
    return "Jobs de engajamento disparados", 200

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    try:
        data = request.json
        if not data:
            logger.warning("⚠️ Webhook vazio")
            return "ok", 200

        update = Update.de_json(data, application.bot)
        asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            loop
        )
        return "ok", 200
    except Exception as e:
        logger.exception(f"🔥 Erro no webhook: {e}")
        return "error", 500

async def setup_webhook():
    global scheduler_started
    
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook antigo removido")
        webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook configurado para: {webhook_url}")
        
        # Inicia o scheduler de engajamento (apenas uma vez)
        if not scheduler_started:
            asyncio.create_task(engagement_scheduler(application.bot))
            scheduler_started = True
            logger.info("✅ Scheduler de engajamento iniciado")
            
    except Exception as e:
        logger.error(f"❌ Erro ao configurar webhook: {e}")

if __name__ == "__main__":
    asyncio.run_coroutine_threadsafe(application.initialize(), loop)
    asyncio.run_coroutine_threadsafe(application.start(), loop)
    
    # Inicia o scheduler junto com o bot
    asyncio.run_coroutine_threadsafe(
        engagement_scheduler(application.bot),
        loop
    )
    
    logger.info(f"🌐 Iniciando Flask na porta {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
