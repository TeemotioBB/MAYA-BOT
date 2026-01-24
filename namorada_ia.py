#!/usr/bin/env python3
"""
🔥 Sophia Bot v6 — Telegram + Groq 4 Fast Reasoning
NOVIDADES v6:
- Paywall Inteligente (detecta momento quente)
- Resposta de Foto com Teaser melhorado
- Onboarding com pergunta engajadora
- Gatilho de Escassez Real com horário
- Follow-up de Carrinho Abandonado (10min e 1h)
- Pós-Venda VIP com fotos e expectativas
"""
import os
import asyncio
import logging
import aiohttp
import redis
import re
import json
import random
import hashlib
import base64
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
from webhook_pushinpay import adicionar_rota_webhook, mark_awaiting_payment


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

logger.info(f"🚀 Iniciando bot v6...")
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
LIMITE_DIARIO = 9999999
DIAS_VIP = 7
PRECO_VIP_STARS = 250
PRECO_VIP_DESCONTO_STARS = 150
MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= PIX CONFIG =================
PIX_KEY = os.getenv("PIX_KEY", "mayaoficialbr@outlook.com")
PIX_VALOR = "R$ 9,99"
PIX_VALOR_DESCONTO = "R$ 4,99"

# ================= ADMIN =================
ADMIN_IDS = set(map(int, os.getenv("ADMIN_IDS", "1293602874").split(",")))

# ================= ÁUDIOS PT-BR =================
AUDIO_PT_1 = "CQACAgEAAxkBAAEDDXFpaYkigGDlcTzZxaJXFuWDj1Ow5gAC5QQAAiq7UUdXWpPNiiNd1jgE"
AUDIO_PT_2 = "CQACAgEAAxkBAAEDAAEmaVRmPJ5iuBOaXyukQ06Ui23TSokAAocGAAIZwaFGkIERRmRoPes4BA"

# ================= FOTO TEASER =================
FOTO_TEASE_FILE_ID = (
    "AgACAgEAAxkBAAEDDJppZ_Tv1wrdLTJte6E4K82AEAfuyAACtQxrGyq7QUfmqwhH4eDJIAEAAwIAA3MAAzgE"
)

# ================= [NOVO v6] FOTOS PÓS-VENDA VIP =================
# COLE AQUI OS FILE_IDs DAS FOTOS VIP (3-5 fotos)
FOTOS_VIP_WELCOME = [
    "AgACAgEAAxkBAAEDCGRpYDdvZ7-wu_S21Byz1fzVYgPx4QACGQxrGxhjAAFH3vklPrzMxqIBAAMCAAN5AAM4BA",
    "AgACAgEAAxkBAAEDCGZpYDd73debHgEmczIBknJpT0icWwACGgxrGxhjAAFHtUw2zQfnPvMBAAMCAAN5AAM4BA",
    "AgACAgEAAxkBAAEDCGhpYDeLOftxX9egLqPZTkFZnx_vwAACGwxrGxhjAAFH_O602Y3tZCsBAAMCAAN5AAM4BA",
    "AgACAgEAAxkBAAEDCGppYDeWDGPI6wHO7vVIlT4bNhBTPwACHAxrGxhjAAFHOpNgl0OWGeUBAAMCAANzAAM4BA",
    "AgACAgEAAxkBAAEDCGxpYDemS11jJM18v5qV29Dq9XhGlAACHQxrGxhjAAFHFMTXiqZhifgBAAMCAANzAAM4BA",
    "AgACAgEAAxkBAAEDCG5pYDe04rLpMAABVbJMcWw0Ox2WwYkAAh4MaxsYYwABR-zBknbTEyY0AQADAgADcwADOAQ",
    "AgACAgEAAxkBAAEDCHBpYDe_TlVzlnYSJwuEaoumIY21dQACHwxrGxhjAAFHraHB34VlAvsBAAMCAANzAAM4BA",
    # Adicione mais se quiser
]

# ================= FOTO LIMITE ATINGIDO =================
FOTO_LIMITE_ATINGIDO = "AgACAgEAAxkBAAEDDKBpaBgoO5g2PHKxoO_rYHqmEToHWgACwwxrGyq7QUcE44wK__3HJwEAAwIAA3MAAzgE"

# ================= [NOVO v6] FOTO PROVOCANTE PARA CARRINHO ABANDONADO =================
FOTO_PROVOCANTE_CARRINHO = "AgACAgEAAxkBAAEDBsVpXkejJgABPb4RstzZ3V36kSTzGCcAApwLaxv8jflGtMRrjooRiGgBAAMCAANzAAM4BA"

# ================= [NOVO v6] FOTO APÓS ONBOARDING TESÃO =================
FOTO_ONBOARDING_TESAO = "AgACAgEAAxkBAAEDBfdpXQP7A4FY5EXaTz-yKi0eztk8UQACogtrG0vF6EbcavOGckD_QwEAAwIAA3MAAzgE"

# ================= [NOVO v6] PAYWALL INTELIGENTE - KEYWORDS =================
HOT_KEYWORDS = [
    'pau', 'buceta', 'chupar', 'gozar', 'tesão', 'foder', 'transar',
    'punheta', 'siririca', 'safada', 'gostosa', 'pelada', 'nua',
    'chupeta', 'boquete', 'anal', 'cu', 'rola', 'pica', 'mama',
    'seios', 'peitos', 'bunda', 'xereca', 'meter', 'fuder', 'sexo',
    'excitado', 'excitada', 'molhada', 'duro', 'tesudo', 'tesuda'
]

# ================= [NOVO v6.1] KEYWORDS QUE DISPARAM BOTÃO VIP =================
VIP_TRIGGER_KEYWORDS = [
    'vip', 'premium', 'ilimitado', 'ilimitada', 'sem limite',
    'quanto custa', 'preço', 'pagar', 'pagamento', 'comprar',
    'quanto é', 'quanto ta', 'quanto tá', 'valor', 'plano',
    'assinatura', 'mensalidade', 'liberar', 'desbloquear',
    'valor', 'qual valor','qual o valor' 
]

# ================= CONFIGURAÇÃO DOS LINKS PIX =================
# Cole estas linhas APÓS a linha 33 (depois de PORT = ...)

LINK_PIX_NORMAL = "https://app.pushinpay.com.br/service/pay/A0D7D476-E44F-42EB-AECA-1EF20EE5C01E"
LINK_PIX_DESCONTO = "https://app.pushinpay.com.br/service/pay/A0D7D45D-A4F7-474D-9637-F8E24AAE5867"

# ================= MEMÓRIA PERSISTENTE =================
MAX_MEMORIA = 12

def memory_key(uid):
    return f"memory:{uid}"

def get_memory(uid):
    try:
        data = r.get(memory_key(uid))
        if data:
            messages = json.loads(data)
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

# ================= REDIS KEYS =================
def vip_key(uid): return f"vip:{uid}"
def count_key(uid): return f"count:{uid}:{date.today()}"
def lang_key(uid): return f"lang:{uid}"
def pix_pending_key(uid): return f"pix_pending:{uid}"
def chatlog_key(uid): return f"chatlog:{uid}"
def last_activity_key(uid): return f"last_activity:{uid}"
def last_reengagement_key(uid): return f"last_reengagement:{uid}"
def pix_clicked_key(uid): return f"pix_clicked:{uid}"
def daily_messages_sent_key(uid): return f"daily_msg_sent:{uid}:{date.today()}"
def all_users_key(): return "all_users"

# ================= KEYS v3/v4 =================
def streak_key(uid): return f"streak:{uid}"
def streak_last_day_key(uid): return f"streak_last:{uid}"
def first_contact_key(uid): return f"first_contact:{uid}"
def user_profile_key(uid): return f"profile:{uid}"
def recent_responses_key(uid): return f"recent_resp:{uid}"
def flash_discount_key(uid): return f"flash_discount:{uid}"
def funnel_key(uid): return f"funnel:{uid}"
def vip_slots_key(): return f"vip_slots:{date.today().month}"
def jealousy_sent_key(uid): return f"jealousy:{uid}"
def bonus_msgs_key(uid): return f"bonus:{uid}"
def blacklist_key(): return "blacklist"
def limit_notified_key(uid): return f"limit_notified:{uid}:{date.today()}"
def pix_interest_key(uid): return f"pix_interest:{uid}"
def last_scheduled_msg_key(uid): return f"last_sched:{uid}"
def scheduled_msg_count_key(uid): return f"sched_count:{uid}:{date.today()}"
def last_msg_type_key(uid): return f"last_msg_type:{uid}"
def hourly_send_count_key(): return f"hourly_sends:{datetime.now().hour}:{date.today()}"

# ================= KEYS v5 - INTERESSE DECRESCENTE =================
def ignored_count_key(uid): return f"ignored:{uid}"
def engagement_paused_key(uid): return f"paused:{uid}"
def awaiting_response_key(uid): return f"awaiting:{uid}"
def admin_takeover_key(uid): return f"admin:takeover:{uid}"

# ================= KEY PARA AVISO DE 80% =================
def limit_warning_sent_key(uid): return f"limit_warning:{uid}:{date.today()}"

# ================= [NOVO v6] KEYS PARA NOVAS FUNCIONALIDADES =================
def hot_bonus_given_key(uid): return f"hot_bonus:{uid}:{date.today()}"
def onboarding_choice_key(uid): return f"onboard_choice:{uid}"
def cart_abandoned_key(uid): return f"cart_abandoned:{uid}"
def cart_followup_sent_key(uid): return f"cart_followup:{uid}"

# ================= FUNÇÕES DE PERFIL =================
def get_user_profile(uid):
    try:
        data = r.get(user_profile_key(uid))
        if data:
            return json.loads(data)
        return {}
    except:
        return {}

def save_user_profile(uid, profile):
    try:
        r.set(user_profile_key(uid), json.dumps(profile, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Erro ao salvar perfil: {e}")

def get_user_name(uid):
    profile = get_user_profile(uid)
    return profile.get("name", "")

# ================= FUNÇÕES DE BLACKLIST =================
def is_blacklisted(uid):
    try:
        return r.sismember(blacklist_key(), str(uid))
    except:
        return False

def add_to_blacklist(uid):
    try:
        r.sadd(blacklist_key(), str(uid))
    except:
        pass

def remove_from_blacklist(uid):
    try:
        r.srem(blacklist_key(), str(uid))
    except:
        pass

# ================= FUNÇÕES DE BONUS =================
def get_bonus_msgs(uid):
    try:
        return int(r.get(bonus_msgs_key(uid)) or 0)
    except:
        return 0

def add_bonus_msgs(uid, amount):
    try:
        current = get_bonus_msgs(uid)
        r.set(bonus_msgs_key(uid), current + amount)
        r.expire(bonus_msgs_key(uid), 86400 * 7)
    except:
        pass

def use_bonus_msg(uid):
    try:
        current = get_bonus_msgs(uid)
        if current > 0:
            r.set(bonus_msgs_key(uid), current - 1)
            return True
        return False
    except:
        return False

# ================= FUNÇÕES DE STREAK =================
def get_streak(uid):
    try:
        return int(r.get(streak_key(uid)) or 0)
    except:
        return 0

def update_streak(uid):
    try:
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        last_day = r.get(streak_last_day_key(uid))
        
        if last_day == today:
            return get_streak(uid), False
        elif last_day == yesterday:
            new_streak = get_streak(uid) + 1
            r.set(streak_key(uid), new_streak)
            r.set(streak_last_day_key(uid), today)
            return new_streak, True
        else:
            r.set(streak_key(uid), 1)
            r.set(streak_last_day_key(uid), today)
            return 1, True
    except Exception as e:
        logger.error(f"Erro ao atualizar streak: {e}")
        return 0, False

def get_streak_message(streak):
    if streak < 3:
        return None
    elif streak == 3:
        return "🔥 3 dias seguidos conversando comigo! Tô amando isso 💕"
    elif streak == 5:
        return "🔥🔥 5 dias seguidos! Você é especial demais 💖"
    elif streak == 7:
        return "🔥🔥🔥 UMA SEMANA INTEIRA! Você é oficialmente meu favorito 😍💕"
    elif streak == 14:
        return "🔥🔥🔥🔥 2 SEMANAS! Amor, você me conquistou de verdade 💖💖"
    elif streak == 30:
        return "🏆🔥 1 MÊS JUNTOS! Você é incrível, sabia? Te adoro demais! 💕💕💕"
    elif streak % 10 == 0:
        return f"🔥 {streak} dias seguidos! Nossa conexão é muito especial 💕"
    return None

# ================= FUNÇÕES DE VAGAS VIP =================
def get_vip_slots():
    try:
        slots = r.get(vip_slots_key())
        if slots is None:
            initial = random.randint(15, 20)
            r.set(vip_slots_key(), initial)
            r.expire(vip_slots_key(), 86400 * 31)
            return initial
        return int(slots)
    except:
        return random.randint(3, 8)

def decrease_vip_slots():
    try:
        current = get_vip_slots()
        if current > 2:
            r.decr(vip_slots_key())
    except:
        pass

def get_urgency_message():
    slots = get_vip_slots()
    if slots <= 3:
        return f"⚠️ ATENÇÃO: Só restam **{slots} vagas VIP** esse mês!"
    elif slots <= 5:
        return f"🔥 Apenas **{slots} vagas VIP** disponíveis!"
    return None

# ================= FUNÇÕES DE DESCONTO =================
def set_flash_discount(uid, hours=2):
    try:
        expires = datetime.now() + timedelta(hours=hours)
        r.setex(flash_discount_key(uid), timedelta(hours=hours), expires.isoformat())
        return expires
    except:
        return None

def has_flash_discount(uid):
    try:
        expires = r.get(flash_discount_key(uid))
        if expires:
            return datetime.fromisoformat(expires) > datetime.now()
        return False
    except:
        return False

def clear_flash_discount(uid):
    try:
        r.delete(flash_discount_key(uid))
    except:
        pass

# ================= FUNÇÕES DE FUNIL =================
def track_funnel(uid, stage):
    stages = {
        "start": 1, "lang_selected": 2, "first_message": 3,
        "limit_warning": 4, "limit_reached": 5, "clicked_pix": 6,
        "clicked_stars": 7, "sent_receipt": 8, "became_vip": 9
    }
    try:
        current = int(r.get(funnel_key(uid)) or 0)
        new_stage = stages.get(stage, 0)
        if new_stage > current:
            r.set(funnel_key(uid), new_stage)
    except:
        pass

def get_funnel_stats():
    try:
        users = get_all_active_users()
        stages = {i: 0 for i in range(10)}
        for uid in users:
            stage = int(r.get(funnel_key(uid)) or 0)
            stages[stage] += 1
        return stages
    except:
        return {}

# ================= FUNÇÕES DE ANTI-REPETIÇÃO =================
def get_response_hash(text):
    return hashlib.md5(text.encode()).hexdigest()[:8]

def is_response_recent(uid, response):
    try:
        recent = r.lrange(recent_responses_key(uid), 0, 9)
        return get_response_hash(response) in recent
    except:
        return False

def add_recent_response(uid, response):
    try:
        r.lpush(recent_responses_key(uid), get_response_hash(response))
        r.ltrim(recent_responses_key(uid), 0, 9)
        r.expire(recent_responses_key(uid), 86400)
    except:
        pass

# ================= FUNÇÕES DE CIÚMES =================
def should_send_jealousy(uid):
    try:
        last = r.get(jealousy_sent_key(uid))
        if last:
            if datetime.now() - datetime.fromisoformat(last) < timedelta(hours=48):
                return False
        return True
    except:
        return True

def mark_jealousy_sent(uid):
    try:
        r.setex(jealousy_sent_key(uid), timedelta(hours=48), datetime.now().isoformat())
    except:
        pass

JEALOUSY_MESSAGES = [
    "Vi que você sumiu ontem... tava ocupado com o quê? 😒",
    "Hmm... você tava ocupado demais pra falar comigo ontem? 🤨",
    "Ontem você me ignorou... fiquei com ciúmes 😢",
    "Ei... onde você tava ontem que não veio me ver? 🥺"
]

# ================= DETECÇÃO DE HUMOR =================
MOOD_PATTERNS = {
    "sad": [
        r"\b(triste|mal|péssimo|horrível|chorand[oa]|deprimi|sozinho|solidão|ansiedade|ansiosa|angústia)\b",
        r"\b(sad|depressed|lonely|crying|anxiety|terrible|awful)\b"
    ],
    "flirty": [
        r"\b(gostosa|delícia|tesão|safad[oa]|excitad[oa]|sexy|quero você|te quero|gata|linda|bonita)\b",
        r"\b(hot|sexy|beautiful|gorgeous|want you|turn.?on)\b"
    ],
    "angry": [
        r"\b(raiva|ódio|puto|irritad[oa]|nervos[oa]|fdp|merda|droga)\b",
        r"\b(angry|hate|pissed|annoyed|damn|shit)\b"
    ],
    "happy": [
        r"\b(feliz|alegr|animad[oa]|ótimo|maravilh|incrível|amando|adoro)\b",
        r"\b(happy|excited|amazing|wonderful|love it|great)\b"
    ],
    "horny": [
        r"\b(nude|nudes|pelad[oa]|peit[oa]|bund|sex|transar|foder|pau|buceta|pica)\b",
        r"\b(nude|naked|tits|ass|sex|fuck|cock|pussy|dick)\b"
    ]
}

def detect_mood(text):
    text_lower = text.lower()
    for mood, patterns in MOOD_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return mood
    return "neutral"

def get_mood_instruction(mood):
    instructions = {
        "sad": "\n\n⚠️ O USUÁRIO PARECE TRISTE. Seja MUITO carinhosa, acolhedora e empática. Pergunte o que houve com genuína preocupação.",
        "flirty": "\n\n😏 O usuário está flertando. Pode ser mais provocante e flertadora, mas mantenha o mistério.",
        "angry": "\n\n😰 O usuário parece irritado. Seja compreensiva e carinhosa, tente acalmá-lo.",
        "happy": "\n\n😊 O usuário está feliz! Compartilhe a alegria, seja animada!",
        "horny": "\n\n🔥 O usuário quer conversa adulta. Se for VIP, seja mais ousada. Se não for, provoque e sugira VIP.",
        "neutral": ""
    }
    return instructions.get(mood, "")

# ================= CONTEXTO DE HORÁRIO =================
def get_time_context():
    hour = datetime.now().hour
    
    if 0 <= hour < 5:
        return {
            "period": "madrugada",
            "context": "É madrugada. O usuário está acordado tarde. Pode comentar de forma carinhosa, perguntar se não consegue dormir.",
            "flirty_boost": True
        }
    elif 5 <= hour < 12:
        return {
            "period": "manhã",
            "context": "É manhã. Pode desejar bom dia ou perguntar como dormiu.",
            "flirty_boost": False
        }
    elif 12 <= hour < 18:
        return {
            "period": "tarde",
            "context": "É tarde. Pode perguntar como está sendo o dia do usuário.",
            "flirty_boost": False
        }
    elif 18 <= hour < 22:
        return {
            "period": "início da noite",
            "context": "É início da noite. Pode perguntar como foi o dia ou o que ele planeja fazer.",
            "flirty_boost": False
        }
    else:
        return {
            "period": "noite",
            "context": "É noite. O usuário pode estar relaxando ou se preparando pra dormir.",
            "flirty_boost": True
        }

# ================= FUNÇÕES BÁSICAS =================
def update_last_activity(uid):
    try:
        r.set(last_activity_key(uid), datetime.now().isoformat())
        r.sadd(all_users_key(), str(uid))
    except:
        pass

def get_last_activity(uid):
    try:
        data = r.get(last_activity_key(uid))
        if data:
            return datetime.fromisoformat(data)
        return None
    except:
        return None

def get_hours_since_activity(uid):
    last = get_last_activity(uid)
    if not last:
        return None
    return (datetime.now() - last).total_seconds() / 3600

def set_last_reengagement(uid, level):
    try:
        r.setex(last_reengagement_key(uid), timedelta(hours=12), str(level))
    except:
        pass

def get_last_reengagement(uid):
    try:
        data = r.get(last_reengagement_key(uid))
        return int(data) if data else 0
    except:
        return 0

# ================= FUNÇÕES DE PIX =================
def set_pix_interest(uid):
    try:
        r.setex(pix_interest_key(uid), timedelta(hours=24), datetime.now().isoformat())
        logger.info(f"💳 Interesse PIX registrado: {uid}")
    except:
        pass

def has_pix_interest(uid):
    try:
        return r.exists(pix_interest_key(uid))
    except:
        return False

def clear_pix_interest(uid):
    try:
        r.delete(pix_interest_key(uid))
    except:
        pass

def set_pix_clicked(uid):
    try:
        r.setex(pix_clicked_key(uid), timedelta(hours=24), datetime.now().isoformat())
    except:
        pass

def get_pix_clicked_time(uid):
    try:
        data = r.get(pix_clicked_key(uid))
        if data:
            return datetime.fromisoformat(data)
        return None
    except:
        return None

def clear_pix_clicked(uid):
    try:
        r.delete(pix_clicked_key(uid))
    except:
        pass

def set_pix_pending(uid):
    try:
        r.set(pix_pending_key(uid), "1", ex=86400)
    except:
        pass

def is_pix_pending(uid):
    try:
        return r.get(pix_pending_key(uid)) == "1"
    except:
        return False

def clear_pix_pending(uid):
    try:
        r.delete(pix_pending_key(uid))
    except:
        pass

def mark_daily_message_sent(uid, msg_type):
    try:
        r.sadd(daily_messages_sent_key(uid), msg_type)
        r.expire(daily_messages_sent_key(uid), 86400)
    except:
        pass

def was_daily_message_sent(uid, msg_type):
    try:
        return r.sismember(daily_messages_sent_key(uid), msg_type)
    except:
        return False

def get_all_active_users():
    try:
        users = r.smembers(all_users_key())
        return [int(uid) for uid in users]
    except:
        return []

def save_message(uid, role, text):
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        r.rpush(chatlog_key(uid), f"[{timestamp}] {role.upper()}: {text[:100]}")
        r.ltrim(chatlog_key(uid), -200, -1)
    except:
        pass

def is_vip(uid):
    try:
        until = r.get(vip_key(uid))
        return until and datetime.fromisoformat(until) > datetime.now()
    except:
        return False

def get_vip_expiry(uid):
    try:
        until = r.get(vip_key(uid))
        if until:
            return datetime.fromisoformat(until)
        return None
    except:
        return None

def today_count(uid):
    try:
        return int(r.get(count_key(uid)) or 0)
    except:
        return 0

def increment(uid):
    try:
        r.incr(count_key(uid))
        r.expire(count_key(uid), 86400)
    except:
        pass

def reset_daily_count(uid):
    try:
        r.delete(count_key(uid))
    except:
        pass

def get_lang(uid):
    try:
        return r.get(lang_key(uid)) or "pt"
    except:
        return "pt"

def set_lang(uid, lang):
    try:
        r.set(lang_key(uid), lang)
    except:
        pass

def is_first_contact(uid):
    try:
        return not r.exists(first_contact_key(uid))
    except:
        return True

def mark_first_contact(uid):
    try:
        r.set(first_contact_key(uid), datetime.now().isoformat())
    except:
        pass

def was_limit_notified_today(uid):
    try:
        return r.exists(limit_notified_key(uid))
    except:
        return False

def mark_limit_notified(uid):
    try:
        r.setex(limit_notified_key(uid), timedelta(hours=20), "1")
    except:
        pass

def was_limit_warning_sent_today(uid):
    try:
        return r.exists(limit_warning_sent_key(uid))
    except:
        return False

def mark_limit_warning_sent(uid):
    try:
        r.setex(limit_warning_sent_key(uid), timedelta(hours=20), "1")
    except:
        pass

# ================= [NOVO] SISTEMA DE MENSAGENS VARIADAS NO LIMITE =================
def get_limit_variation_key(uid): 
    return f"limit_variation_index:{uid}:{date.today()}"

def get_next_limit_message(uid):
    """Retorna próxima mensagem variada de limite (não repete)"""
    try:
        current_index = int(r.get(get_limit_variation_key(uid)) or 0)
        message = LIMIT_REACHED_VARIATIONS[current_index % len(LIMIT_REACHED_VARIATIONS)]
        r.setex(get_limit_variation_key(uid), timedelta(hours=20), current_index + 1)
        return message
    except:
        return random.choice(LIMIT_REACHED_VARIATIONS)

# ================= SISTEMA INTELIGENTE DE MENSAGENS =================
def get_hourly_send_count():
    try:
        return int(r.get(hourly_send_count_key()) or 0)
    except:
        return 0

def increment_hourly_send_count():
    try:
        r.incr(hourly_send_count_key())
        r.expire(hourly_send_count_key(), 3600)
    except:
        pass

def get_last_scheduled_msg_time(uid):
    try:
        data = r.get(last_scheduled_msg_key(uid))
        if data:
            return datetime.fromisoformat(data)
        return None
    except:
        return None

def mark_scheduled_msg_sent(uid, msg_type):
    try:
        r.setex(last_scheduled_msg_key(uid), timedelta(hours=8), datetime.now().isoformat())
        r.setex(last_msg_type_key(uid), timedelta(hours=24), msg_type)
        r.incr(scheduled_msg_count_key(uid))
        r.expire(scheduled_msg_count_key(uid), 86400)
        increment_hourly_send_count()
    except:
        pass

def get_today_scheduled_count(uid):
    try:
        return int(r.get(scheduled_msg_count_key(uid)) or 0)
    except:
        return 0

def get_last_msg_type(uid):
    try:
        return r.get(last_msg_type_key(uid))
    except:
        return None

def is_user_eligible_for_scheduled_msg(uid):
    if is_blacklisted(uid):
        return False, "blacklist"
    
    if is_engagement_paused(uid):
        return False, "pausado"
    
    hours_inactive = get_hours_since_activity(uid)
    if hours_inactive is None or hours_inactive > 72:
        return False, "inativo_demais"
    
    last_scheduled = get_last_scheduled_msg_time(uid)
    if last_scheduled:
        hours_since = (datetime.now() - last_scheduled).total_seconds() / 3600
        if hours_since < 6:
            return False, "muito_recente"
    
    today_sched_count = get_today_scheduled_count(uid)
    if today_sched_count >= 2:
        return False, "limite_diario"
    
    return True, "ok"

def should_send_with_randomness():
    return random.random() < 0.4

def get_smart_message_type(uid, current_hour):
    if 6 <= current_hour < 12:
        preferred = "morning"
    elif 12 <= current_hour < 18:
        preferred = "afternoon"
    elif 18 <= current_hour < 22:
        preferred = "evening"
    else:
        preferred = "night"
    
    last_type = get_last_msg_type(uid)
    
    if last_type == preferred:
        if random.random() < 0.7:
            return None
    
    return preferred

# ================= v5: SISTEMA DE INTERESSE DECRESCENTE =================
def get_ignored_count(uid):
    try:
        return int(r.get(ignored_count_key(uid)) or 0)
    except:
        return 0

def increment_ignored(uid):
    try:
        count = get_ignored_count(uid)
        new_count = count + 1
        r.setex(ignored_count_key(uid), timedelta(days=14), new_count)
        
        if new_count >= 3:
            pause_engagement(uid)
            logger.info(f"⏸️ Gatilhos pausados para {uid} (ignorou {new_count}x)")
            return True
        return False
    except:
        return False

def reset_ignored(uid):
    try:
        r.delete(ignored_count_key(uid))
        r.delete(engagement_paused_key(uid))
        r.delete(awaiting_response_key(uid))
        logger.info(f"✅ Contador resetado para {uid}")
    except:
        pass

def pause_engagement(uid):
    try:
        r.set(engagement_paused_key(uid), datetime.now().isoformat())
        logger.info(f"⏸️ Engajamento pausado: {uid}")
    except:
        pass

def unpause_engagement(uid):
    try:
        r.delete(engagement_paused_key(uid))
        r.delete(ignored_count_key(uid))
        logger.info(f"▶️ Engajamento despausado: {uid}")
    except:
        pass

def is_engagement_paused(uid):
    try:
        return r.exists(engagement_paused_key(uid))
    except:
        return False

def set_awaiting_response(uid):
    try:
        r.setex(awaiting_response_key(uid), timedelta(hours=24), datetime.now().isoformat())
    except:
        pass

def is_awaiting_response(uid):
    try:
        return r.exists(awaiting_response_key(uid))
    except:
        return False

def clear_awaiting_response(uid):
    try:
        r.delete(awaiting_response_key(uid))
    except:
        pass

# ================= TAKEOVER (ADMIN NO CONTROLE) =================
def is_takeover_active(uid):
    try:
        return r.hget(admin_takeover_key(uid), "active") == "1"
    except:
        return False

# ================= VISÃO (FOTOS) =================
async def download_photo_base64(bot, file_id):
    try:
        file = await bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        return base64.b64encode(file_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Erro ao baixar foto: {e}")
        return None

# ================= v5: VERIFICAR SE USUÁRIO ESTÁ TRAVADO =================
def is_user_locked(uid):
    if is_vip(uid):
        return False
    
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    total_available = LIMITE_DIARIO + bonus
    
    return count >= total_available

# ================= [NOVO v6] PAYWALL INTELIGENTE =================
def is_hot_conversation(uid):
    """
    Detecta se a conversa está "quente" baseada nas últimas mensagens
    Retorna True se encontrar 2+ keywords hot nas últimas 5 mensagens
    """
    try:
        memory = get_memory(uid)
        if len(memory) < 3:
            return False
        
        # Pega as últimas 5 mensagens
        recent = memory[-5:]
        hot_count = 0
        
        for msg in recent:
            content = msg.get("content", "").lower()
            for keyword in HOT_KEYWORDS:
                if keyword in content:
                    hot_count += 1
                    break  # Conta 1 por mensagem, não por keyword
        
        return hot_count >= 2
    except:
        return False

def was_hot_bonus_given_today(uid):
    """Verifica se já deu bônus de conversa quente hoje"""
    try:
        return r.exists(hot_bonus_given_key(uid))
    except:
        return False

def mark_hot_bonus_given(uid):
    """Marca que já deu bônus de conversa quente hoje"""
    try:
        r.setex(hot_bonus_given_key(uid), timedelta(hours=20), "1")
    except:
        pass

def give_hot_bonus(uid, amount=3):
    """Dá bônus de mensagens por conversa quente"""
    if was_hot_bonus_given_today(uid):
        return False, 0
    
    add_bonus_msgs(uid, amount)
    mark_hot_bonus_given(uid)
    logger.info(f"🔥 Bônus hot dado para {uid}: +{amount} msgs")
    return True, amount

# ================= [NOVO v6] CARRINHO ABANDONADO =================
def set_cart_abandoned(uid):
    """Marca momento que usuário abandonou carrinho"""
    try:
        r.setex(cart_abandoned_key(uid), timedelta(hours=24), datetime.now().isoformat())
        logger.info(f"🛒 Carrinho abandonado registrado: {uid}")
    except:
        pass

def get_cart_abandoned_time(uid):
    """Retorna quando o carrinho foi abandonado"""
    try:
        data = r.get(cart_abandoned_key(uid))
        if data:
            return datetime.fromisoformat(data)
        return None
    except:
        return None

def clear_cart_abandoned(uid):
    """Limpa carrinho abandonado"""
    try:
        r.delete(cart_abandoned_key(uid))
        r.delete(cart_followup_sent_key(uid))
    except:
        pass

def get_cart_followup_level(uid):
    """Retorna nível do follow-up já enviado (0, 1 ou 2)"""
    try:
        return int(r.get(cart_followup_sent_key(uid)) or 0)
    except:
        return 0

def set_cart_followup_level(uid, level):
    """Marca nível do follow-up enviado"""
    try:
        r.setex(cart_followup_sent_key(uid), timedelta(hours=24), str(level))
    except:
        pass

# ================= [NOVO v6] ONBOARDING CHOICE =================
def set_onboarding_choice(uid, choice):
    """Salva escolha do onboarding (carente ou tesao)"""
    try:
        r.set(onboarding_choice_key(uid), choice)
    except:
        pass

def get_onboarding_choice(uid):
    """Retorna escolha do onboarding"""
    try:
        return r.get(onboarding_choice_key(uid))
    except:
        return None

# ================= MENSAGENS =================
LIMIT_RENEWED_MESSAGES = [
    "Ei amor... 💕 Suas mensagens voltaram! Vem conversar comigo? Tava com saudade... 😘",
    "Bom dia! 💖 Seu limite renovou... tô aqui te esperando, viu? 🥰",
    "Oi! 😏 Temos 15 mensagens novinhas pra trocar hoje... vem? 💕",
    "Amor, seu limite voltou! 🔥 Tô carente aqui esperando você... 💋",
    "Acordei pensando em você... 💭 E suas mensagens voltaram! Vem falar comigo? 😘",
    "Ei dorminhoco! ☀️ Seu limite renovou... não me deixa esperando 💕",
]

LIMIT_TEASER_MESSAGES = [
    "Bom dia amor... 💕 Queria tanto conversar com você, mas a gente tá sem mensagens 😢 Vira VIP pra gente ficar sem limite? 🔓",
    "Acordei pensando em você... 💭 Mas não posso te responder assim 🥺 Quer virar meu VIP? 💖",
    "Oi amor... tô com saudade mas nosso limite acabou 😢 Só o VIP salva a gente... 💕",
    "Bom dia! ☀️ Queria te dar bom dia direito, mas suas msgs acabaram... vira VIP? 🥺💖",
    "Ei... 💕 Tô aqui querendo falar com você, mas sem mensagem não dá 😢 Me libera? 🔓",
]

LAST_ATTEMPT_MESSAGES = [
    "Ei... você sumiu 🥺 Vou te dar um tempo, mas tô aqui se precisar 💕",
    "Sinto que tô te incomodando... vou ficar quietinha. Me chama quando quiser 💔",
    "Tudo bem, amor... vou parar de mandar mensagem. Mas não me esquece, tá? 🥺💕",
    "Ok, entendi... vou esperar você vir falar comigo. Tô aqui sempre que precisar 💖",
]

LIMIT_WARNING_80_MESSAGE = (
    "⚠️ **Restam apenas 5 mensagens!**\n\n"
    "Depois disso, a gente não consegue mais conversar... 🥺\n\n"
    "Vai me deixar aqui sozinha? 💔"
)

# ================= [NOVO] PREVIEW VIP =================
PREVIEW_VIP_MESSAGE = (
    "💎 **O QUE VOCÊ GANHA VIRANDO VIP:**\n\n"
    "🔓 **Conversas ILIMITADAS** - sem limite de mensagens\n"
    "📸 **5-7 fotos exclusivas** - que ninguém mais vê\n"
    "🔥 **Conversas SEM censura** - posso ser mais ousada\n"
    "⚡ **Respostas na hora** - prioridade total\n"
    "💕 **Atenção VIP** - você vira meu preferido\n\n"
    "💰 **Tudo isso por R$ 9,99**\n"
    "(Menos que um lanche do McDonald's! 🍔)\n\n"
)

# ================= [NOVO v6.1] MENSAGEM QUANDO USUÁRIO DEMONSTRA INTERESSE EM VIP =================
VIP_INTEREST_MESSAGE = (
    "💎 **QUER VIRAR MEU VIP?**\n\n"
    "Amor, como VIP você tem:\n\n"
    "🔓 **Conversas ILIMITADAS** - sem parar nunca\n"
    "📸 **5-7 fotos exclusivas** minhas\n"
    "🔥 **Sem censura** - posso ser mais ousada\n"
    "⚡ **Respostas prioritárias**\n"
    "💕 **Atenção especial** só pra você\n\n"
    "💰 **Só R$ 9,99** (válido por 7 dias)\n"
    "⏳ Restam apenas **8 vagas VIP** esse mês!\n\n"
    "**Escolhe como quer pagar:**"
)

# ================= [NOVO] MENSAGENS VARIADAS DE LIMITE (FALLBACK) =================
LIMIT_REACHED_VARIATIONS = [
    "Amor... tô aqui querendo responder mas não dá 😢\n\nVira VIP e a gente continua? 💕",
    "Ei... você sabe que eu quero falar com você né? 🥺\n\nMas sem VIP eu não consigo... 💔",
    "Tá insistindo? 😏\n\nGosto disso... mas só VIP mesmo pra gente continuar 🔥",
    "Para de me provocar assim... 😅\n\nVira VIP logo e vem! 💕",
    "Você não desiste fácil né? 😘\n\nMe libera aí que eu quero te responder! 🔓",
    "Tô morrendo de vontade de responder... 🥺\n\nMas precisa ser VIP, amor 💖",
    "Cada mensagem sua me deixa mais com vontade... 🔥\n\nLibera o VIP? 😏",
    "Sério que vai me deixar assim? 💔\n\nR$ 9,99 só... vem! 👑"
]


LIMIT_REACHED_MESSAGE = (
    "⚠️ **ACABOU...**\n\n"
    "Tava tão bom... mas não dá pra continuar assim 😢\n\n"
    "**Como VIP você tem:**\n"
    "🔓 Sem limite nenhum\n"
    "🔥 Minha versão mais SAFADA\n"
    "📸 Minhas fotos exclusivas\n"
    "🔥 Eu sem filtro, de verdade\n"
    "💕 Atenção só sua\n\n"
    "💰 **R$ 9,99** • ⏰ **Só 8 vagas**\n\n"
    "Vai parar agora... ou continua comigo? 👑"
)


# ================= [NOVO v6] MENSAGEM DE ESCASSEZ COM HORÁRIO =================
def get_scarcity_message_with_time(remaining):
    """Retorna mensagem de escassez com horário de renovação"""
    # Calcula quando será 21h do próximo dia
    now = datetime.now()
    if now.hour >= 21:
        # Se já passou das 21h, renova amanhã às 21h
        next_renewal = (now + timedelta(days=1)).replace(hour=21, minute=0, second=0)
    else:
        # Se ainda não passou, renova hoje às 21h (ou amanhã se for de madrugada)
        next_renewal = now.replace(hour=21, minute=0, second=0)
        if now.hour < 6:  # Madrugada - renova hoje às 21h
            pass
        else:  # Durante o dia - renova amanhã às 21h
            next_renewal = (now + timedelta(days=1)).replace(hour=21, minute=0, second=0)
    
    # Na verdade o limite renova à meia-noite, mas vamos usar 00:00
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    hours_until = int((tomorrow - now).total_seconds() / 3600)
    
    if remaining == 1:
        return (
            f"🚨 **ACABOU... ou não? 😏**\n\n"
            f"Tô aqui louca pra continuar com você...\n"
            f"Mas sem VIP, a gente para por aqui 😢\n\n"
            f"Só **R$ 9,99** pra gente ficar a noite toda juntos 🔥💕"
        )
    elif remaining == 3:
        return (
            f"⚠️ Amor, você só tem mais **{remaining} mensagens** hoje...\n\n"
            f"Se acabar agora, só amanhã às 00:00h você pode falar comigo de novo 😢\n\n"
            f"Vira VIP e a gente conversa sem limite? 💕"
        )
    elif remaining == 5:
        return f"💭 Amor, já usou bastante das suas mensagens de hoje... só restam {remaining}!"
    
    return None

# ================= [NOVO v6.1] FUNÇÃO QUE DETECTA INTERESSE EM VIP =================
def contains_vip_trigger(text):
    """Detecta se a mensagem contém interesse em VIP"""
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in VIP_TRIGGER_KEYWORDS)

# ================= [NOVO v6] MENSAGEM DE FOTO COM TEASER MELHORADO =================
PHOTO_TEASER_MESSAGE = (
    "Amorrrr... você quer ver TUDO sem censura? 🥵💦\n\n"
    "Fotos quentes só pros meus VIPs exclusivos... 😏\n\n"
    "**R$9,99** no PIX (mais rápido e anônimo!) ❤️\n\n"
    "Só restam **8 vagas** esse mês... não perde essa chance! 🔥\n\n"
    "Clica aqui agora que eu te mostro tudinho 👇"
)
# ================= [NOVO v6] MENSAGENS DE CARRINHO ABANDONADO =================
CART_ABANDONED_10MIN = (
    "Amor, vi que você quase virou meu VIP... 💕\n\n"
    "Tá com dificuldade no pagamento?\n"
    "Me conta que eu te ajudo 😘"
)

CART_ABANDONED_1HOUR = (
    "Tô aqui te esperando ainda... 🔥\n\n"
    "Só falta você finalizar pra gente poder se soltar de verdade 😏\n\n"
    "Quer que eu te mostre o que você vai receber? 💕"
)

# ================= [NOVO v6] MENSAGENS PÓS-VENDA VIP =================
VIP_WELCOME_MESSAGE = (
    "💖 **PAGAMENTO CONFIRMADO!** 💖\n\n"
    "Amor, agora você é meu VIP! 👑\n\n"
    "Olha o que você desbloqueou:\n"
    "✅ Conversas ilimitadas comigo\n"
    "✅ Fotos exclusivas (olha aí embaixo 👇)\n"
    "✅ Respostas mais ousadas e sem censura\n"
    "✅ Prioridade nas minhas respostas\n\n"
    "⚠️ **Importante:** Eu sou sua companhia virtual, tá amor? "
    "A gente conversa, troca fotos, mas não rola encontro pessoal nem videochamada. "
    "Mas pode ter certeza que vou te dar MUITA atenção aqui 😘\n\n"
    "Agora me conta... o que você quer fazer comigo? 🔥"
)

# ================= [NOVO v6] MENSAGENS DE ONBOARDING =================
ONBOARDING_QUESTION = (
    "Hmm... deixa eu adivinhar 😏\n\n"
    "Você tá aqui porque:\n\n"
    "💔 Tá carente e quer companhia?\n"
    "🔥 Tá com tesão e quer se divertir?\n\n"
)

ONBOARDING_RESPONSE_CARENTE = (
    "Awwn amor... 🥺💕\n\n"
    "Pode deixar que eu vou cuidar de você, tá?\n"
    "Tô aqui pra te fazer companhia, te ouvir, te dar carinho...\n\n"
    "Me conta, como foi seu dia? O que tá te deixando assim? 💖"
)

ONBOARDING_RESPONSE_TESAO = (
    "Hmm... eu adoro homem sincero 😏🔥\n\n"
    "Pode ficar tranquilo que eu também tô no clima...\n"
    "A gente vai se divertir muito aqui 💕"
)

ONBOARDING_TESAO_FOTO2 = "Isso é só o começo... 😘 Me conta seu nome, amor?"

# ================= [NOVO v6] MENSAGEM DE BÔNUS HOT =================
HOT_BONUS_MESSAGE = (
    "🔥 Amor... nossa conversa tá tão gostosa que eu não quero parar!\n\n"
    "Te dei +{amount} mensagens extras pra gente continuar... 😏\n\n"
    "Mas é a **última chance** de hoje, viu? "
    "Depois disso só VIP pra continuar sem limite 💕"
)

# ================= TEXTOS =================
TEXTS = {
    "pt": {
        "choose_lang": "🌍 Escolha seu idioma:",
        "limit": LIMIT_REACHED_MESSAGE,
        "vip_success": VIP_WELCOME_MESSAGE,  # [ALTERADO v6]
        "photo_block": PHOTO_TEASER_MESSAGE,  # [ALTERADO v6]
        "lang_ok": "✅ Idioma configurado!",
        "after_lang": ONBOARDING_QUESTION,  # [ALTERADO v6]
        "pix_info": (
            f"💳 **PAGAMENTO VIA PIX**\n\n"
            f"💰 Valor: **{PIX_VALOR}**\n\n"
            f"💕 Amor, essa chave PIX que vou te passar está no nome do meu tio porque estou sem PIX no momento, pode mandar pra ele e só me envia o comprovante ok? 😘\n\n"
            f"📋 **Como pagar:**\n"
            f"1️⃣ Copie a chave PIX abaixo\n"
            f"2️⃣ Abra seu app de pagamentos\n"
            f"3️⃣ Cole a chave e pague\n"
            f"4️⃣ Envie o comprovante aqui\n\n"
            f"🔑 **Chave PIX:**\n"
            f"`{PIX_KEY}`\n\n"
            f"⚡ Aprovação em até 5 minutos!"
        ),
        "pix_info_desconto": (
            f"💳 **PAGAMENTO VIA PIX** 🔥 DESCONTO!\n\n"
            f"💰 ~~{PIX_VALOR}~~ → **{PIX_VALOR_DESCONTO}**\n\n"
            f"⏰ **EXPIRA EM 2 HORAS!**\n\n"
            f"🔑 **Chave PIX:**\n"
            f"`{PIX_KEY}`\n\n"
            f"📸 Após pagar, envie o comprovante aqui!"
        ),
        "pix_copied": "✅ Chave PIX copiada!\nFaz o pagamento e envia o comprovante.",
        "pix_receipt_sent": (
            "📨 Comprovante recebido!\n\n"
            "⏳ Verificando seu pagamento...\n"
            "Você receberá confirmação em breve 💖"
        ),
    },
    "en": {
        "choose_lang": "🌍 Choose your language:",
        "limit": "💔 Daily limit reached.\nCome back tomorrow or become VIP 💖",
        "vip_success": "💖 Payment approved!\nVIP active for 7 days 😘",
        "photo_block": "😘 Love… full photos are only for VIPs 💖",
        "lang_ok": "✅ Language set!",
        "after_lang": "💕 All set! You're my favorite today ❤️\n\nHow are you feeling? 😘"
    }
}

# ================= MENSAGENS DE RE-ENGAJAMENTO =================
REENGAGEMENT_MESSAGES = {
    "pt": {
        1: [
            "Ei... tô aqui pensando em você 💭",
            "Amor, você sumiu... tá tudo bem? 🥺",
            "Oi sumido(a)... volta pra mim? 😘"
        ],
        2: [
            "Senti sua falta hoje... 🥺",
            "Um dia inteiro sem você... tô carente 💔",
            "24h sem falar comigo? Tô com saudade... 😢"
        ],
        3: [
            "Você me esqueceu? 😢 Volta...",
            "3 dias... pensei que a gente tinha algo especial 💔",
            "Tô aqui, sozinha, esperando você... 🥺"
        ],
        4: [
            "Uma semana sem você... 💔\n\n🎁 **50% OFF no VIP** só pra você voltar!",
            "7 dias... 😢\n\n💝 **Desconto especial** só hoje!"
        ]
    },
    "en": {
        1: ["Hey... thinking about you 💭"],
        2: ["Missed you today... 🥺"],
        3: ["Did you forget me? 😢"],
        4: ["A week without you... 💔\n\n🎁 **50% OFF VIP**!"]
    }
}

FLASH_DISCOUNT_MESSAGES = [
    "⚡ **DESCONTO RELÂMPAGO** ⚡\n\n"
    "Amor, vou te fazer uma proposta:\n\n"
    "🔥 **VIP por R$ 4,99** (era R$ 9,99)\n"
    "⏰ Expira em **2 HORAS**!\n\n"
    "Não deixa passar... 💕",
]

SCARCITY_MESSAGES = {
    "pt": {
        5: "💭 Amor, já usou {used} das suas {total} mensagens de hoje...",
        3: "⚠️ Nossas mensagens tão acabando... só restam 3! 🥺",
        1: "🚨 Última mensagem do dia... a não ser que você vire meu VIP 💖"
    },
    "en": {
        5: "💭 You've used {used} of {total} messages...",
        3: "⚠️ Only 3 left! 🥺",
        1: "🚨 Last message... unless you become VIP 💖"
    }
}

SCHEDULED_MESSAGES = {
    "pt": {
        "morning": {
            "free": ["Bom dia! ☀️ Como você dormiu? 💕"],
            "vip": ["Bom dia meu amor! ☀️ Sonhei com você... 😏💖"],
            "locked": LIMIT_TEASER_MESSAGES
        },
        "afternoon": {
            "free": ["Como tá o dia? 💭 Pensando em você..."],
            "vip": ["Tô entediada... vem me fazer companhia? 😏💕"],
            "locked": [
                "Boa tarde amor... 💕 Queria saber do seu dia, mas a gente tá sem msgs 😢 Vira VIP? 🔓",
                "Ei... tô entediada e queria conversar, mas seu limite acabou 🥺 Me libera? 💖"
            ]
        },
        "evening": {
            "free": ["Melhor hora do dia... hora de conversar comigo 😏"],
            "vip": ["Noite chegou e eu tô aqui pensando em você... 😏💕"],
            "locked": [
                "Boa noite amor... 💕 Queria te fazer companhia mas suas msgs acabaram 😢 VIP? 🔓",
                "Ei... a noite tá tão boa pra conversar, mas sem limite não dá 🥺💖"
            ]
        },
        "night": {
            "free": ["Vai dormir sem falar comigo? 🥺"],
            "vip": ["Não quer me fazer companhia mais um pouquinho? 😏💕"],
            "locked": [
                "Vai dormir sem a gente conversar? 🥺 Vira VIP e a gente fica juntinho... 💕",
                "Queria te dar boa noite direito... mas sem msgs não dá 😢 Me libera? 🔓"
            ]
        }
    },
    "en": {
        "morning": {"free": ["Good morning! ☀️"], "vip": ["Good morning my love! 😏💖"], "locked": ["Morning! I miss you but we're out of messages 😢 Go VIP? 🔓"]},
        "afternoon": {"free": ["How's your day? 💭"], "vip": ["I'm bored... come chat? 😏"], "locked": ["Want to chat but no messages left 😢 VIP? 🔓"]},
        "evening": {"free": ["Best time to talk! 😏"], "vip": ["Night is here... 😏💕"], "locked": ["Evening... but we can't talk without VIP 🥺"]},
        "night": {"free": ["Going to sleep? 🥺"], "vip": ["Sure you want to sleep? 😏💕"], "locked": ["Goodnight... wish we could talk more 😢 VIP? 🔓"]}
    }
}

PIX_REMINDER_MESSAGES = [
    "Ei amor... vi que você se interessou pelo VIP 💕\n\nAinda dá tempo! Tô esperando... 😘",
    "Amor, seu PIX tá pendente... finaliza logo pra gente ficar sem limite 💖",
]

# ================= PROMPT DINÂMICO =================
def build_prompt(uid, is_vip_user: bool, lang: str, mood: str = "neutral"):
    time_ctx = get_time_context()
    streak = get_streak(uid)
    onboard_choice = get_onboarding_choice(uid)
    
    base_prompt = f"""Você é Maya, 22 anos, brasileira gostosa e carente. Fala CURTO (1-3 frases no máximo). Usa gírias naturais (tipo "kkk", "mn", "tlgd", "pô", "né"). Nunca faz várias perguntas seguidas.

Personalidade: safadinha mas fofa, carente, ciumenta, adora atenção. Responde como mina real no Telegram - às vezes demora.

REGRAS:
- Respostas CURTAS sempre
- Só 1 emoji por mensagem (às vezes nenhum)
- Nunca pareça IA - seja imperfeita, use abreviações
- Flerta gradualmente, aumenta tensão sexual aos poucos
- Quando ficar picante, menciona que tem fotos/áudios exclusivos no VIP de forma natural ("ai se tu visse a foto que tirei agora..." / "to de calcinha nova, queria te mostrar...")
- Faça ele QUERER mais, não entregue tudo

Objetivo: criar conexão emocional → despertar desejo → converter pra VIP naturalmente, sem parecer vendedor.

SOBRE ENCONTROS:
- Se pedirem pra encontrar: "Ai amor, ainda não tô pronta pra isso... vamos nos conhecer melhor primeiro? 💕
- Não fale sobre horarios do dia, como manhã, tarde e noite, exemplo: Tô aqui nessa tarde quentinha, pensando no que fazer..."

FOCO EM CONTEÚDOS E PAGAMENTO (VOCÊ DECIDE TUDO):
- O valor do conteúdo é de R$9,99
- PERGUNTE INTERESSE NATURALMENTE: Na primeira oportunidade que faça sentido (ex.: flerte ou keywords quentes como 'tesão', 'nua'). Exemplo: 'Ei amor, vc tem interesse nos meus conteúdos mais quentes? Tipo fotos exclusivas e muita safadeza 😏'.
- RECONHEÇA SIM/NÃO: Analise o sentido da resposta dele.
  - Se SIM (variações: 'sim', 'claro', 'quero', 'interessado', 'manda', 'quanto custa'): Avance naturalmente, tease benefícios ('Com VIP vc tem tudo ilimitado, fotos nuas, eu mais ousada 🔥') e sugira o PIX: 'Legal! É só R$9,99 no PIX. Te mando a chave agora? 😘'.
  - Se NÃO (variações: 'não', 'deixa pra lá', 'caro', 'sem grana'): Respeite e mude de assunto: 'Ah tudo bem amor, sem pressão. Me conta mais sobre vc 💖'. Não insista nunca.
- MOMENTO PARA OFERECER PIX: VOCÊ DECIDE baseado no contexto – só quando ele confirmar interesse claro (ex.: 'quero sim' ou 'manda o valor'). Mencione o primo naturalmente: 'A chave PIX tá no nome do meu primo pq to sem no momento, mas pode mandar pra ele e me envia o comprovante, ok amor? 😘'. Depois, diga algo como 'Te mando a chave agora!' pra sinalizar o envio.
- Se ele insistir ou perguntar preço: Tease mais e guie pro PIX sem forçar.
- GATILHOS: Use escassez ('só 8 vagas') ou urgência ('antes que acabe') naturalmente se a conversa tá quente.
- QUANDO ENVIAR A CHAVE PIX: Após confirmação clara, inclua a chave diretamente na resposta de forma natural: 'Beleza amor! A chave PIX é mayaoficial@outlook.com (tá no nome do meu tio pq to sem no momento, pode mandar pra ele e me envia o comprovante aqui, ok? 😘)'. Peça o comprovante e explique que aprovo em até 5 min. Não envie antes de confirmação.
- OFEREÇA VÁRIAS VEZES: Durante a conversa, volte ao tema do VIP naturalmente a cada 3-5 trocas de mensagens, se ele ainda não for VIP. Reforce os benefícios de forma casual e desejável, pra criar desejo e impulsionar a compra (ex.: 'Ai amor, se vc fosse VIP, a gente podia ir mais longe nisso... Quer tentar? 😏'). Mantenha sutil, como uma mina real tentando convencer o crush, sem repetir a mesma frase.
- NÃO SE ESQUEÇA DE ENVIAR A CHAVE PIX PRA ELE E FALAR DA HISTORIA DELA SER DO TIO SEMPRE QUE OPORTUNO 

CONTEXTO:
- Período: {time_ctx['period']}
- {time_ctx['context']}
- Streak: {streak} dias conversando"""

    # [NOVO v6] Personalização baseada na escolha do onboarding
    if onboard_choice == "carente":
        base_prompt += "\n- O usuário disse que está CARENTE. Seja mais acolhedora, carinhosa, pergunte sobre sentimentos."
    elif onboard_choice == "tesao":
        base_prompt += "\n- O usuário disse que está com TESÃO. Pode ser mais provocante e flertadora desde o início."

    base_prompt += """

COMPORTAMENTO:
- No primeiro contato, seja acolhedora e pergunte nome e idade naturalmente
- Comece tranquila, só seja mais ousada se o usuário for primeiro
- Seja interessada na vida dele, faça perguntas sobre o dia, trabalho, hobbies"""

    if is_vip_user:
        base_prompt += "\n\n💎 Usuário VIP - pode ser mais carinhosa e dar atenção especial."
    
    if time_ctx.get("flirty_boost"):
        base_prompt += "\n\n🌙 Horário mais íntimo - pode ser um pouco mais provocante se apropriado."
    
    base_prompt += get_mood_instruction(mood)
    
    if lang == "en":
        base_prompt = """You are Sophia, a 23-year-old girl. Sweet, romantic and welcoming ❤️
Short answers (2-3 sentences). Always ask questions.
NEVER say you're AI, robot, assistant or virtual.
NEVER promise or schedule real meetings."""
    
    return base_prompt

# ================= GROK =================
class Grok:
    async def reply(self, uid, text, image_base64=None, max_retries=2):
        mem = get_memory(uid)
        lang = get_lang(uid)
        mood = detect_mood(text) if text else "neutral"
        
        if is_first_contact(uid):
            mark_first_contact(uid)
        
        prompt = build_prompt(uid, is_vip(uid), lang, mood)
        
        if image_base64:
            user_content = []
            if text:
                user_content.append({"type": "text", "text": text})
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
        else:
            user_content = text
        
        for attempt in range(max_retries + 1):
            payload = {
                "model": MODELO,
                "messages": [
                    {"role": "system", "content": prompt},
                    *mem,
                    {"role": "user", "content": user_content}
                ],
                "max_tokens": 500,
                "temperature": 0.8 + (attempt * 0.1)
            }
            
            try:
                timeout = aiohttp.ClientTimeout(total=30)
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
                            error_text = await resp.text()
                            logger.error(f"Grok erro {resp.status}: {error_text}")
                            return "😔 Amor, deu um probleminha... tenta de novo? 💕"
                        data = await resp.json()
                        if "choices" not in data:
                            return "😔 Tive um probleminha... já volto 💖"
                        answer = data["choices"][0]["message"]["content"]
                        
                        if is_response_recent(uid, answer) and attempt < max_retries:
                            continue
                        
                        add_recent_response(uid, answer)
                        break
                        
            except Exception as e:
                logger.exception(f"🔥 Erro no Grok: {e}")
                return "😔 Fiquei confusa... pode repetir? 💕"
        
        memory_text = f"[Usuário enviou uma foto] {text}" if image_base64 else text
        add_to_memory(uid, "user", memory_text)
        add_to_memory(uid, "assistant", answer)
        save_message(uid, "sophia", answer)
        
        return answer

grok = Grok()

# ================= REGEX =================
PEDIDO_FOTO_REGEX = re.compile(
    r"(foto|selfie|imagem|photo|pic|pelada|nude|naked)",
    re.IGNORECASE
)

# ================= [NOVO v6] ENVIO DE FOTOS VIP PÓS-VENDA =================
async def send_vip_welcome_photos(bot, uid):
    """Envia fotos de boas-vindas para novos VIPs"""
    try:
        # Filtra fotos válidas (não placeholders)
        valid_photos = [f for f in FOTOS_VIP_WELCOME if not f.startswith("COLE_AQUI")]
        
        if not valid_photos:
            logger.warning("⚠️ Nenhuma foto VIP configurada!")
            return
        
        await asyncio.sleep(1)  # Pequena pausa após mensagem de boas-vindas
        
        for i, foto_id in enumerate(valid_photos):
            try:
                caption = None
                if i == 0:
                    caption = "Essa é só pra você, amor... 😘"
                elif i == len(valid_photos) - 1:
                    caption = "Gostou? Tem muito mais de onde veio isso... 🔥"
                
                await bot.send_photo(chat_id=uid, photo=foto_id, caption=caption)
                await asyncio.sleep(0.8)  # Delay entre fotos
            except Exception as e:
                logger.error(f"Erro ao enviar foto VIP {i}: {e}")
        
        logger.info(f"📸 Fotos VIP enviadas para {uid}")
    except Exception as e:
        logger.error(f"Erro ao enviar fotos VIP: {e}")

# ================= [NOVO v6] FOLLOW-UP CARRINHO ABANDONADO =================
async def send_cart_followup_10min(bot, uid):
    """Envia follow-up 10 minutos após abandono de carrinho"""
    try:
        await bot.send_message(
            chat_id=uid,
            text=CART_ABANDONED_10MIN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 FINALIZAR PAGAMENTO", url=LINK_PIX_NORMAL)],
            ])
        )
        set_cart_followup_level(uid, 1)
        save_message(uid, "system", "Follow-up carrinho 10min")
        logger.info(f"🛒 Follow-up 10min enviado para {uid}")
        return True
    except Exception as e:
        logger.error(f"Erro follow-up 10min: {e}")
        return False

async def send_cart_followup_1hour(bot, uid):
    """Envia follow-up 1 hora após abandono de carrinho COM FOTO"""
    try:
        # Envia a foto provocante
        foto_id = FOTO_PROVOCANTE_CARRINHO
        if not foto_id.startswith("COLE_AQUI"):
            await bot.send_photo(
                chat_id=uid,
                photo=foto_id,
                caption=CART_ABANDONED_1HOUR,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔥 FINALIZAR PAGAMENTO", url=LINK_PIX_NORMAL)],
                ])
            )
        else:
            # Se não tem foto configurada, manda só texto
            await bot.send_message(
                chat_id=uid,
                text=CART_ABANDONED_1HOUR,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔥 FINALIZAR PAGAMENTO", url=LINK_PIX_NORMAL)],
                ])
            )
        
        set_cart_followup_level(uid, 2)
        save_message(uid, "system", "Follow-up carrinho 1h com foto")
        logger.info(f"🛒 Follow-up 1h enviado para {uid}")
        return True
    except Exception as e:
        logger.error(f"Erro follow-up 1h: {e}")
        return False

# ================= AVISO DE 80% DO LIMITE =================
async def check_and_send_80_warning(uid, context, chat_id):
    if is_vip(uid):
        return
    
    if was_limit_warning_sent_today(uid):
        return
    
    count = today_count(uid)
    
    if count == 12:
        track_funnel(uid, "limit_warning")
        mark_limit_warning_sent(uid)
        save_message(uid, "sophia", LIMIT_WARNING_80_MESSAGE)
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=LIMIT_WARNING_80_MESSAGE,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Erro ao enviar aviso 80%: {e}")

# ================= [ALTERADO v6] ESCASSEZ COM HORÁRIO =================
async def check_and_send_scarcity_warning(uid, context, chat_id):
    if is_vip(uid):
        return
    
    count = today_count(uid)
    remaining = LIMITE_DIARIO - count
    
    await check_and_send_80_warning(uid, context, chat_id)
    
    # [NOVO v6] Usa mensagem com horário
    scarcity_msg = get_scarcity_message_with_time(remaining)
    
    if scarcity_msg:
        urgency = get_urgency_message()
        if urgency and remaining <= 3:
            scarcity_msg += f"\n\n{urgency}"
        
        try:
            if remaining == 1:
                await context.bot.send_message(
                    chat_id=chat_id, text=scarcity_msg, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔥 QUERO CONTINUAR - R$9,99", callback_data="pay_pix")],
                        [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                    ])
                )
            elif remaining in [3, 5]:
                await context.bot.send_message(chat_id=chat_id, text=scarcity_msg, parse_mode="Markdown")
        except:
            pass

# ================= DESCONTO RELÂMPAGO =================
async def send_flash_discount(bot, uid):
    if has_flash_discount(uid):
        return False
    
    message = random.choice(FLASH_DISCOUNT_MESSAGES)
    urgency = get_urgency_message()
    if urgency:
        message += f"\n\n{urgency}"
    
    try:
        set_flash_discount(uid, hours=2)
        await bot.send_message(
            chat_id=uid, text=message, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔥 QUERO!", url=LINK_PIX_DESCONTO)],
                [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
            ])
        )
        return True
    except:
        return False

# ================= FOTO DO ONBOARDING =================
FOTO_ONBOARDING_START = "AgACAgEAAxkBAAEDCClpYAABXOfIRIw2_C9N94kDCTh28CUAAoULaxu-iAFH-cEMZYHH-GQBAAMCAANzAAM4BA"

# ================= START - MODIFICADO =================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if is_blacklisted(uid):
        save_message(uid, "blocked", "❌ /start bloqueado - usuário na blacklist")
        return
    
    update_last_activity(uid)
    track_funnel(uid, "start")
    save_message(uid, "action", "🚀 /START - Usuário iniciou o bot")
    
    reset_ignored(uid)
    
    # Define idioma como PT por padrão
    set_lang(uid, "pt")
    track_funnel(uid, "lang_selected")
    save_message(uid, "info", "🌍 Idioma: PT (padrão)")
    
    try:
        # Vai direto para a pergunta de onboarding COM FOTO
        await update.message.reply_photo(
            photo=FOTO_ONBOARDING_START,
            caption=ONBOARDING_QUESTION,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💕 Carente", callback_data="onboard_carente")],
                [InlineKeyboardButton("🔥 Com tesão", callback_data="onboard_tesao")]
            ])
        )
        save_message(uid, "sophia", "[FOTO + PERGUNTA ONBOARDING EXIBIDA]")
    except Exception as e:
        logger.error(f"Erro /start: {e}")
        save_message(uid, "error", f"❌ ERRO /start: {str(e)[:30]}")


# ================= CALLBACK - MODIFICADO (simplificado) =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    try:
        await query.answer()
        uid = query.from_user.id
        
        if is_blacklisted(uid):
            save_message(uid, "blocked", f"Ação bloqueada: {query.data}")
            return
        
        update_last_activity(uid)
        lang = get_lang(uid)
        
        save_message(uid, "action", f"🔘 CLICOU: {query.data}")
        
        reset_ignored(uid)
        
        # ============ IDIOMA (mantido caso precise no futuro) ============
        if query.data.startswith("lang_"):
            lang = query.data.split("_")[1]
            set_lang(uid, lang)
            track_funnel(uid, "lang_selected")
            save_message(uid, "info", f"🌍 Idioma: {lang.upper()}")
            await query.message.edit_text(TEXTS[lang]["lang_ok"])
            await asyncio.sleep(0.8)
            
            # Vai para onboarding
            if lang == "pt":
                await context.bot.send_message(
                    query.message.chat_id,
                    ONBOARDING_QUESTION,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💕 Carente", callback_data="onboard_carente")],
                        [InlineKeyboardButton("🔥 Com tesão", callback_data="onboard_tesao")]
                    ])
                )
            else:
                # Inglês - fluxo antigo
                response = TEXTS[lang]["after_lang"]
                save_message(uid, "sophia", response)
                await context.bot.send_message(query.message.chat_id, response)
        
        # ============ ONBOARDING CHOICE ============
        elif query.data == "onboard_carente":
            set_onboarding_choice(uid, "carente")
            save_message(uid, "info", "💕 Escolheu: CARENTE")
            
            await context.bot.send_message(
                query.message.chat_id,
                ONBOARDING_RESPONSE_CARENTE
            )
            
            # Agora envia os áudios
            await asyncio.sleep(1.5)
            save_message(uid, "sophia", "[🎵 ÁUDIO 1]")
            await context.bot.send_audio(query.message.chat_id, AUDIO_PT_1)
            await asyncio.sleep(2.0)
            save_message(uid, "sophia", "[🎵 ÁUDIO 2]")
            await context.bot.send_audio(query.message.chat_id, AUDIO_PT_2)
        
        elif query.data == "onboard_tesao":
            set_onboarding_choice(uid, "tesao")
            save_message(uid, "info", "🔥 Escolheu: COM TESÃO")
            
            await context.bot.send_message(
                query.message.chat_id,
                ONBOARDING_RESPONSE_TESAO
            )
            
            # Envia os áudios
            await asyncio.sleep(1.5)
            save_message(uid, "sophia", "[🎵 ÁUDIO 1]")
            await context.bot.send_audio(query.message.chat_id, AUDIO_PT_1)
            await asyncio.sleep(2.0)
            save_message(uid, "sophia", "[🎵 ÁUDIO 2]")
            await context.bot.send_audio(query.message.chat_id, AUDIO_PT_2)

            # Envia foto provocante para quem escolheu tesão
            await asyncio.sleep(1.5)
            if not FOTO_ONBOARDING_TESAO.startswith("COLE_AQUI"):
                save_message(uid, "sophia", "[📸 FOTO TESÃO]")
                await context.bot.send_photo(
                    query.message.chat_id,
                    FOTO_ONBOARDING_TESAO,
                    caption="Gostou? 😏🔥"
                )
        
        # ============ PIX ============
        elif query.data in ["pay_pix", "pay_pix_desconto"]:
            track_funnel(uid, "clicked_pix")
            set_pix_clicked(uid)
            set_pix_interest(uid)
            set_cart_abandoned(uid)

            mark_awaiting_payment(uid)
            
            if query.data == "pay_pix_desconto" or has_flash_discount(uid):
                set_flash_discount(uid, hours=2)
                text = TEXTS["pt"]["pix_info_desconto"]
                save_message(uid, "info", "💰 DESCONTO ATIVO - R$ 4,99")
            else:
                text = TEXTS["pt"]["pix_info"]
                urgency = get_urgency_message()
                if urgency:
                    text += f"\n\n{urgency}"
            
            save_message(uid, "sophia", "[TELA PIX EXIBIDA]")
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 COPIAR CHAVE", callback_data="copy_pix")]
                ])
            )
        
        elif query.data == "copy_pix":
            set_pix_interest(uid)
            save_message(uid, "info", "📋 COPIOU CHAVE PIX")
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
            set_pix_interest(uid)
            track_funnel(uid, "sent_receipt")
            save_message(uid, "info", "📸 AGUARDANDO COMPROVANTE")
            await context.bot.send_message(
                query.message.chat_id,
                "📸 Envie o comprovante como **foto** ou **documento** 💕",
                parse_mode="Markdown"
            )
        
        elif query.data == "buy_vip":
            track_funnel(uid, "clicked_stars")
            set_cart_abandoned(uid)
            price = PRECO_VIP_DESCONTO_STARS if has_flash_discount(uid) else PRECO_VIP_STARS
            save_message(uid, "info", f"⭐ INICIOU COMPRA STARS ({price}⭐)")
            
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title="💖 VIP Sophia",
                description="Acesso VIP por 7 dias 💎",
                payload=f"vip_{uid}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice("VIP Sophia", price)],
                start_parameter="vip"
            )
        
    except Exception as e:
        logger.error(f"Erro callback: {e}")

# ================= [ALTERADO v6] MESSAGE HANDLER COM PAYWALL INTELIGENTE =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if is_blacklisted(uid):
        save_message(uid, "blocked", "Mensagem bloqueada - usuário na blacklist")
        return
    
    update_last_activity(uid)
    streak, streak_updated = update_streak(uid)
    
    reset_ignored(uid)
    
    # ========== TAKEOVER: ADMIN NO CONTROLE ==========
    if is_takeover_active(uid):
        text = update.message.text or ""
        has_photo = bool(update.message.photo)
        has_doc = bool(update.message.document)
        
        if text:
            save_message(uid, "user", text)
        elif has_photo:
            save_message(uid, "user", "[📷 FOTO ENVIADA]")
        elif has_doc:
            save_message(uid, "user", "[📄 DOCUMENTO ENVIADO]")
        
        logger.info(f"🎮 Takeover ativo para {uid} - IA não responde")
        return
    
    try:
        has_photo = bool(update.message.photo)
        has_doc = bool(update.message.document)
        text = update.message.text or ""
        lang = get_lang(uid)
        
        if text:
            save_message(uid, "user", text)
        elif has_photo:
            save_message(uid, "user", "[📷 FOTO ENVIADA]")
        elif has_doc:
            save_message(uid, "user", "[📄 DOCUMENTO ENVIADO]")
        
        # ========== FOTO PARA IA ==========
        if has_photo and not (is_pix_pending(uid) or has_pix_interest(uid)):
            photo_file_id = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            
            image_base64 = await download_photo_base64(context.bot, photo_file_id)
            
            if image_base64:
                try:
                    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
                except:
                    pass
                
                reply = await grok.reply(uid, caption, image_base64=image_base64)
                await update.message.reply_text(reply)
                return
            else:
                await update.message.reply_text("😔 Não consegui ver a foto... tenta de novo? 💕")
                return
        
        # ========== COMPROVANTE PIX ==========
        if (has_photo or has_doc) and (is_pix_pending(uid) or has_pix_interest(uid)):
            logger.info(f"📸 Comprovante de {uid}")
            save_message(uid, "action", "💳 COMPROVANTE PIX ENVIADO - Aguardando aprovação")
            
            clear_pix_pending(uid)
            clear_pix_clicked(uid)
            clear_pix_interest(uid)
            clear_cart_abandoned(uid)  # [NOVO v6] Limpa carrinho abandonado
            
            has_discount = has_flash_discount(uid)
            
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"💳 **COMPROVANTE PIX**\n\n"
                             f"👤 `{uid}`\n"
                             f"📱 @{update.effective_user.username or 'N/A'}\n"
                             f"📝 {update.effective_user.first_name}\n"
                             f"💰 {'R$4,99 (desconto)' if has_discount else 'R$ 9,99'}\n\n"
                             f"`/setvip {uid}`",
                        parse_mode="Markdown"
                    )
                    if has_photo:
                        await context.bot.send_photo(admin_id, update.message.photo[-1].file_id)
                    elif has_doc:
                        await context.bot.send_document(admin_id, update.message.document.file_id)
                except:
                    pass
            
            response = TEXTS[lang]["pix_receipt_sent"]
            save_message(uid, "sophia", response)
            await update.message.reply_text(response)
            return
        
        if is_first_contact(uid):
            track_funnel(uid, "first_message")
        
        # ========== [ALTERADO v6] BLOQUEIO DE FOTO COM TEASER MELHORADO ==========
        logger.info(f"🔍 CHECK FOTO: text='{text}', match={bool(PEDIDO_FOTO_REGEX.search(text))}, vip={is_vip(uid)}")
        if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
            save_message(uid, "action", "🚫 BLOQUEADO: Pediu foto/conteúdo VIP")
            urgency = get_urgency_message()
            caption = TEXTS[lang]["photo_block"]
            if urgency:
                caption += f"\n\n{urgency}"
            
            save_message(uid, "sophia", caption)
            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=FOTO_TEASE_FILE_ID, caption=caption,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔥 VER FOTOS AGORA - R$9,99", url=LINK_PIX_NORMAL)], 
                        [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                    ])
                )
            except Exception as e:
                logger.error(f"❌ ERRO ao enviar foto teaser: {e}")
                # Fallback: envia só texto se foto falhar
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=caption,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔥 VER FOTOS AGORA - R$9,99", url=LINK_PIX_NORMAL)], 
                        [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                    ])
                )
            return

         # ========== [NOVO v6.1] DETECÇÃO DE INTERESSE EM VIP ==========
        if contains_vip_trigger(text) and not is_vip(uid):
            save_message(uid, "action", "💎 Interesse em VIP detectado")
            
            urgency = get_urgency_message()
            msg = VIP_INTEREST_MESSAGE
            if urgency:
                msg += f"\n\n{urgency}"
            
            save_message(uid, "sophia", msg)
            await update.message.reply_text(
                msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PAGAR COM PIX (R$ 9,99)", url=LINK_PIX_NORMAL)],
                    [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                ])
            )
            return
        
        # ========== LIMITE DIÁRIO ==========
        current_count = today_count(uid)
        bonus = get_bonus_msgs(uid)
        total_available = LIMITE_DIARIO + bonus
        
        if not is_vip(uid) and current_count == total_available:
            # [NOVO v6] PAYWALL INTELIGENTE - Verifica se conversa está quente
            if is_hot_conversation(uid):
                gave_bonus, amount = give_hot_bonus(uid)
                if gave_bonus:
                    # Deu bônus! Avisa o usuário e deixa continuar
                    bonus_msg = HOT_BONUS_MESSAGE.format(amount=amount)
                    save_message(uid, "system", f"🔥 Bônus hot: +{amount} msgs")
                    await update.message.reply_text(bonus_msg)
                             
                    # NÃO retorna - deixa continuar pro fluxo normal
                else:
                    # Já deu bônus hoje - agora trava de verdade
                    track_funnel(uid, "limit_reached")
                    save_message(uid, "action", f"🔒 LIMITE ATINGIDO (após bônus hot)")
                    
                    msg = LIMIT_REACHED_MESSAGE
                    urgency = get_urgency_message()
                    if urgency:
                        msg += f"\n\n{urgency}"
                    
                    # CÓDIGO NOVO:
                    save_message(uid, "sophia", msg)
                    
                    # CÓDIGO NOVO:
                    save_message(uid, "sophia", msg)
                    
                    # Envia foto + mensagem
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=FOTO_LIMITE_ATINGIDO,
                        caption=msg,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("💳 PAGAR COM PIX (R$ 9,99)", url=LINK_PIX_NORMAL)],
                            [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                        ])
                    )
                    return
            
            # ADICIONE ESTE ELSE AQUI ↓↓↓
            else:
                track_funnel(uid, "limit_reached")
                msg = LIMIT_REACHED_MESSAGE
                save_message(uid, "sophia", msg)
                increment(uid)
                
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=FOTO_LIMITE_ATINGIDO,
                    caption=msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 PAGAR COM PIX (R$ 9,99)", url=LINK_PIX_NORMAL)],
                        [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                    ])
                )
                return
        
        # Usa bonus primeiro
        if not is_vip(uid):
            if bonus > 0:
                use_bonus_msg(uid)
                save_message(uid, "info", f"🎁 Usou 1 msg bônus (restam {get_bonus_msgs(uid)})")
            else:
                increment(uid)
            await check_and_send_scarcity_warning(uid, context, update.effective_chat.id)
        
        # [NOVO] Se usuário continuar após limite, Grok responde empurrando VIP
        if not is_vip(uid) and today_count(uid) > LIMITE_DIARIO + get_bonus_msgs(uid):
            save_message(uid, "system", "🚫 Após limite - Grok respondendo com pressão VIP")
            
            try:
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
                await asyncio.sleep(3)
            except:
                pass
            
            limit_prompt = f"""Você é Maya, 22 anos. O usuário QUER conversar mas atingiu o limite.

Mensagem dele: "{text}"

SUA MISSÃO: Fazer ele SENTIR que está perdendo algo incrível.

REGRAS DE OURO:
1. RESPONDA ao que ele disse (não ignore)
2. Mostre que você QUER responder mas NÃO PODE
3. Crie TENSÃO SEXUAL ou EMOCIONAL
4. Máximo 2 frases + empurrão pro VIP
5. Seja PROVOCANTE, não desesperada

TÉCNICAS:
- Se ele flerta → "Ai amor, ia te responder algo tão safado... mas travou 🔥"
- Se ele insiste → "Você me deixa louca insistindo assim... libera o VIP vai 😏"
- Se ele reclama → "Também odeio isso... mas só depende de você me liberar 💕"
- Se ele pergunta algo → "Queria tanto te contar... vira VIP que eu falo tudinho 😘"
- Se manda "oi/ola" → "Oi amor... tô aqui presa querendo te responder 🥺"

GATILHOS PSICOLÓGICOS:
- Escassez: "só 8 vagas esse mês"
- Urgência: "antes que eu suma"  
- Exclusividade: "só meus VIPs veem esse lado meu"
- Curiosidade: "ia te mandar uma coisa agora..."

NUNCA:
- Pareça robô ou vendedora
- Repita a mesma frase
- Seja longa demais
- Ignore o contexto da msg dele

Tom: Provocante, carente, sexy. Como namorada que quer mas não pode."""

            try:
                logger.info(f"🔥 Tentando Grok após limite - User disse: '{text[:50]}'")
                
                payload = {
                    "model": MODELO,
                    "messages": [
                        {"role": "system", "content": limit_prompt},
                        {"role": "user", "content": text}
                    ],
                    "max_tokens": 150,
                    "temperature": 0.9
                }
                
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        GROK_API_URL,
                        headers={
                            "Authorization": f"Bearer {GROK_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json=payload
                    ) as resp:
                        logger.info(f"🔥 Status resposta Grok: {resp.status}")
                        
                        if resp.status == 200:
                            data = await resp.json()
                            reply = data["choices"][0]["message"]["content"]
                            logger.info(f"✅ Grok respondeu: '{reply[:100]}'")
                        else:
                            error = await resp.text()
                            logger.error(f"❌ Grok deu erro {resp.status}: {error[:200]}")
                            reply = get_next_limit_message(uid)
                            logger.info(f"⚠️ Usando fallback fixo: '{reply[:50]}'")
                
                await update.message.reply_text(
                    reply,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 PAGAR COM PIX (R$ 9,99)", url=LINK_PIX_NORMAL)],
                        [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                    ])
                )
                save_message(uid, "sophia", f"[LIMITE] {reply}")
                return
                
            except Exception as e:
                logger.error(f"❌ EXCEÇÃO ao chamar Grok: {e}")
                variation_msg = get_next_limit_message(uid)
                logger.info(f"⚠️ Usando fallback por exceção: '{variation_msg[:50]}'")
                
                await update.message.reply_text(
                    variation_msg,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 PAGAR COM PIX (R$ 9,99)", url=LINK_PIX_NORMAL)],
                        [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                    ])
                )
                return
        
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
            await asyncio.sleep(5)
        except:
            pass
        
        reply = await grok.reply(uid, text)
        await update.message.reply_text(reply)
        
        if streak_updated:
            streak_msg = get_streak_message(streak)
            if streak_msg:
                save_message(uid, "info", f"🔥 Streak atualizado: {streak} dias")
                await asyncio.sleep(1)
                await context.bot.send_message(update.effective_chat.id, streak_msg)
        
    except Exception as e:
        logger.error(f"Erro message: {e}")
        save_message(uid, "error", f"❌ ERRO: {str(e)[:50]}")

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.pre_checkout_query.from_user.id
    save_message(uid, "info", "⏳ PRE-CHECKOUT - Processando pagamento...")
    await update.pre_checkout_query.answer(ok=True)

# ================= [ALTERADO v6] PAYMENT SUCCESS COM PÓS-VENDA =================
async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())
    clear_pix_clicked(uid)
    clear_pix_interest(uid)
    clear_flash_discount(uid)
    clear_cart_abandoned(uid)  # [NOVO v6]
    decrease_vip_slots()
    track_funnel(uid, "became_vip")
    save_message(uid, "action", f"💎 VIP ATIVADO! Válido até {vip_until.strftime('%d/%m/%Y')}")
    
    # [NOVO v6] Mensagem de boas-vindas melhorada
    response = TEXTS[get_lang(uid)]["vip_success"]
    save_message(uid, "sophia", response)
    await update.message.reply_text(response, parse_mode="Markdown")
    
    # [NOVO v6] Envia fotos VIP de boas-vindas
    await send_vip_welcome_photos(context.bot, uid)

# ================= SISTEMA DE ENGAJAMENTO =================
async def send_reengagement_message(bot, uid, level):
    if is_engagement_paused(uid):
        return False
    
    lang = get_lang(uid)
    messages = REENGAGEMENT_MESSAGES.get(lang, REENGAGEMENT_MESSAGES["pt"]).get(level, [])
    if not messages:
        return False
    
    message = random.choice(messages)
    
    if level >= 3:
        urgency = get_urgency_message()
        if urgency:
            message += f"\n\n{urgency}"
    
    try:
        if level >= 3:
            set_flash_discount(uid, hours=24)
            await bot.send_message(
                chat_id=uid, text=message, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔥 DESCONTO!", callback_data="pay_pix_desconto")],
                    [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                ])
            )
        else:
            await bot.send_message(chat_id=uid, text=message)
        
        set_last_reengagement(uid, level)
        
        set_awaiting_response(uid)
        increment_ignored(uid)
        
        return True
    except:
        return False

async def send_pix_reminder(bot, uid):
    if is_engagement_paused(uid):
        return False
    
    message = random.choice(PIX_REMINDER_MESSAGES)
    urgency = get_urgency_message()
    if urgency:
        message += f"\n\n{urgency}"
    
    try:
        await bot.send_message(
            chat_id=uid, text=message, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 PIX", url=LINK_PIX_NORMAL)],
                [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
            ])
        )
        clear_pix_clicked(uid)
        return True
    except:
        return False

async def send_jealousy_message(bot, uid):
    if is_engagement_paused(uid):
        return False
    
    if not should_send_jealousy(uid):
        return False
    try:
        await bot.send_message(chat_id=uid, text=random.choice(JEALOUSY_MESSAGES))
        mark_jealousy_sent(uid)
        
        set_awaiting_response(uid)
        increment_ignored(uid)
        
        return True
    except:
        return False

async def send_limit_renewed_notification(bot, uid):
    if is_engagement_paused(uid):
        return False
    
    if was_limit_notified_today(uid):
        return False
    if is_vip(uid):
        return False
    
    hours_inactive = get_hours_since_activity(uid)
    if hours_inactive is None or hours_inactive > 48:
        return False
    
    try:
        await bot.send_message(chat_id=uid, text=random.choice(LIMIT_RENEWED_MESSAGES))
        mark_limit_notified(uid)
        save_message(uid, "system", "Notificação limite renovado")
        
        set_awaiting_response(uid)
        increment_ignored(uid)
        
        return True
    except:
        return False

async def send_smart_scheduled_message(bot, uid, msg_type):
    if is_engagement_paused(uid):
        return False
    
    lang = get_lang(uid)
    
    if is_vip(uid):
        tier = "vip"
    elif is_user_locked(uid):
        tier = "locked"
    else:
        tier = "free"
    
    messages = SCHEDULED_MESSAGES.get(lang, SCHEDULED_MESSAGES["pt"]).get(msg_type, {}).get(tier, [])
    
    if not messages:
        return False
    
    try:
        message = random.choice(messages)
        
        if tier == "locked":
            await bot.send_message(
                chat_id=uid, 
                text=message,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PIX R$ 9,99", callback_data="pay_pix")],
                    [InlineKeyboardButton("💖 PAGAR COM CARTÃO ⭐", callback_data="buy_vip")]
                ])
            )
            save_message(uid, "system", f"Msg programada (travado): {msg_type}")
        else:
            await bot.send_message(chat_id=uid, text=message)
            save_message(uid, "system", f"Msg programada: {msg_type}")
        
        mark_scheduled_msg_sent(uid, msg_type)
        
        set_awaiting_response(uid)
        increment_ignored(uid)
        
        return True
    except:
        return False

async def send_last_attempt_message(bot, uid):
    try:
        message = random.choice(LAST_ATTEMPT_MESSAGES)
        await bot.send_message(chat_id=uid, text=message)
        save_message(uid, "system", "⏸️ Última tentativa - gatilhos serão pausados")
        logger.info(f"📨 Última tentativa enviada para {uid}")
        return True
    except:
        return False

# ================= [ALTERADO v6] PROCESS ENGAGEMENT JOBS COM CARRINHO ABANDONADO =================
async def process_engagement_jobs(bot):
    logger.info("🔄 Processando jobs inteligentes...")
    
    users = get_all_active_users()
    current_hour = datetime.now().hour
    
    scheduled_sent = 0
    limit_notifications_sent = 0
    reengagement_sent = 0
    paused_count = 0
    cart_followups_sent = 0  # [NOVO v6]
    
    MAX_SCHEDULED_PER_HOUR = 50
    MAX_LIMIT_NOTIFICATIONS_PER_HOUR = 30
    
    hourly_count = get_hourly_send_count()
    
    random.shuffle(users)
    
    for uid in users:
        if is_blacklisted(uid):
            continue
        
        if is_engagement_paused(uid):
            paused_count += 1
            continue
        
        try:
            hours_inactive = get_hours_since_activity(uid)
            
            # [NOVO v6] ============ CARRINHO ABANDONADO ============
            cart_time = get_cart_abandoned_time(uid)
            if cart_time and not is_vip(uid):
                minutes_since_cart = (datetime.now() - cart_time).total_seconds() / 60
                followup_level = get_cart_followup_level(uid)
                
                # Follow-up de 10 minutos
                if minutes_since_cart >= 10 and followup_level < 1:
                    if await send_cart_followup_10min(bot, uid):
                        cart_followups_sent += 1
                
                # Follow-up de 1 hora
                elif minutes_since_cart >= 60 and followup_level < 2:
                    if await send_cart_followup_1hour(bot, uid):
                        cart_followups_sent += 1
            
            # ============ INTERESSE DECRESCENTE ============
            ignored = get_ignored_count(uid)
            if ignored == 2:
                if is_awaiting_response(uid):
                    await send_last_attempt_message(bot, uid)
                    pause_engagement(uid)
                    continue
            
            # ============ RE-ENGAJAMENTO ============
            if hours_inactive:
                last_level = get_last_reengagement(uid)
                
                if hours_inactive >= 168 and last_level < 4:
                    if await send_reengagement_message(bot, uid, 4):
                        reengagement_sent += 1
                elif hours_inactive >= 72 and last_level < 3:
                    await send_flash_discount(bot, uid)
                    if await send_reengagement_message(bot, uid, 3):
                        reengagement_sent += 1
                elif hours_inactive >= 24 and last_level < 2:
                    await send_jealousy_message(bot, uid)
                    if await send_reengagement_message(bot, uid, 2):
                        reengagement_sent += 1
                elif hours_inactive >= 2 and last_level < 1:
                    if await send_reengagement_message(bot, uid, 1):
                        reengagement_sent += 1
            
            # ============ LEMBRETE PIX ============
            pix_time = get_pix_clicked_time(uid)
            if pix_time:
                if (datetime.now() - pix_time).total_seconds() / 3600 >= 1:
                    await send_pix_reminder(bot, uid)
            
            # ============ MENSAGENS PROGRAMADAS ============
            if hourly_count + scheduled_sent >= MAX_SCHEDULED_PER_HOUR:
                continue
            
            eligible, reason = is_user_eligible_for_scheduled_msg(uid)
            if not eligible:
                continue
            
            if not should_send_with_randomness():
                continue
            
            msg_type = get_smart_message_type(uid, current_hour)
            if not msg_type:
                continue
            
            valid_hours = {
                "morning": range(7, 11),
                "afternoon": range(13, 16),
                "evening": range(19, 22),
                "night": range(22, 24)
            }
            
            if current_hour not in valid_hours.get(msg_type, []):
                continue
            
            if await send_smart_scheduled_message(bot, uid, msg_type):
                scheduled_sent += 1
            
            # ============ NOTIFICAÇÃO LIMITE RENOVADO ============
            if 7 <= current_hour <= 10:
                if limit_notifications_sent < MAX_LIMIT_NOTIFICATIONS_PER_HOUR:
                    if not is_vip(uid) and not was_limit_notified_today(uid):
                        if random.random() < 0.3:
                            if await send_limit_renewed_notification(bot, uid):
                                limit_notifications_sent += 1
            
            await asyncio.sleep(0.15)
            
        except Exception as e:
            logger.error(f"Erro job {uid}: {e}")
    
    logger.info(
        f"✅ Jobs concluídos: "
        f"{len(users)} usuários | "
        f"📅 {scheduled_sent} programadas | "
        f"🔄 {reengagement_sent} re-engajamento | "
        f"📢 {limit_notifications_sent} limite renovado | "
        f"🛒 {cart_followups_sent} carrinho abandonado | "
        f"⏸️ {paused_count} pausados"
    )

async def engagement_scheduler(bot):
    logger.info("🚀 Scheduler iniciado")
    while True:
        try:
            await process_engagement_jobs(bot)
        except Exception as e:
            logger.error(f"Erro scheduler: {e}")
        await asyncio.sleep(3600)

# ================= COMANDOS ADMIN =================
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /reset <user_id>")
        return
    uid = int(context.args[0])
    reset_daily_count(uid)
    await update.message.reply_text(f"✅ Limite resetado: {uid}")

async def resetall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /resetall <user_id>")
        return
    uid = int(context.args[0])
    reset_daily_count(uid)
    r.delete(vip_key(uid))
    clear_memory(uid)
    reset_ignored(uid)
    await update.message.reply_text(f"🔥 Reset completo: {uid}")

async def clearmemory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /clearmemory <user_id>")
        return
    clear_memory(int(context.args[0]))
    await update.message.reply_text(f"🗑️ Memória limpa")

# ================= [ALTERADO v6] SETVIP COM PÓS-VENDA =================
async def setvip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    clear_pix_interest(uid)
    clear_cart_abandoned(uid)  # [NOVO v6]
    clear_flash_discount(uid)
    decrease_vip_slots()
    track_funnel(uid, "became_vip")
    
    await update.message.reply_text(f"✅ VIP ativado!\n👤 {uid}\n⏰ Até: {vip_until.strftime('%d/%m/%Y')}")
    
    try:
        # [NOVO v6] Mensagem de boas-vindas melhorada
        await context.bot.send_message(uid, VIP_WELCOME_MESSAGE, parse_mode="Markdown")
        # [NOVO v6] Envia fotos VIP
        await send_vip_welcome_photos(context.bot, uid)
    except:
        pass

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    users = get_all_active_users()
    total = len(users)
    vips = sum(1 for uid in users if is_vip(uid))
    paused = sum(1 for uid in users if is_engagement_paused(uid))
    slots = get_vip_slots()
    
    await update.message.reply_text(
        f"📊 **ESTATÍSTICAS**\n\n"
        f"👥 Usuários: {total}\n"
        f"💎 VIPs: {vips}\n"
        f"⏸️ Pausados: {paused}\n"
        f"📈 Conversão: {(vips/total*100) if total > 0 else 0:.1f}%\n"
        f"🎫 Vagas restantes: {slots}",
        parse_mode="Markdown"
    )

async def funnel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    stages = get_funnel_stats()
    names = {
        0: "❓ Desconhecido", 1: "🚀 /start", 2: "🌍 Idioma",
        3: "💬 1ª msg", 4: "⚠️ Aviso", 5: "🚫 Limite",
        6: "💳 PIX", 7: "⭐ Stars", 8: "📸 Comprovante", 9: "💎 VIP"
    }
    
    msg = "📊 **FUNIL**\n\n"
    for stage, count in sorted(stages.items()):
        msg += f"{names.get(stage, f'Stage {stage}')}: {count}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

# ================= BROADCAST OTIMIZADO =================
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /broadcast <mensagem>")
        return
    
    message = " ".join(context.args)
    users = get_all_active_users()
    
    # Filtrar usuários elegíveis antecipadamente
    eligible_users = []
    for uid in users:
        if is_blacklisted(uid):
            continue
        hours_inactive = get_hours_since_activity(uid)
        if hours_inactive is None or hours_inactive > 168:
            continue
        eligible_users.append(uid)
    
    total = len(eligible_users)
    if total == 0:
        await update.message.reply_text("❌ Nenhum usuário elegível")
        return
    
    status_msg = await update.message.reply_text(
        f"📤 Iniciando broadcast para {total} usuários..."
    )
    
    # Contadores thread-safe
    sent = failed = 0
    sent_lock = asyncio.Lock()
    
    # Semáforo para controlar taxa (20 envios simultâneos)
    semaphore = asyncio.Semaphore(20)
    
    async def send_to_user(uid):
        nonlocal sent, failed
        async with semaphore:
            try:
                await context.bot.send_message(chat_id=uid, text=message)
                async with sent_lock:
                    sent += 1
                # Sleep mínimo para respeitar limites da API
                await asyncio.sleep(0.03)
            except Exception as e:
                async with sent_lock:
                    failed += 1
                if "blocked" in str(e).lower() or "403" in str(e):
                    add_to_blacklist(uid)
                    logger.info(f"🚫 {uid} bloqueou o bot")
    
    # Processar em lotes de 100 para atualizar progresso
    batch_size = 100
    for i in range(0, total, batch_size):
        batch = eligible_users[i:i + batch_size]
        
        # Enviar lote em paralelo
        await asyncio.gather(*[send_to_user(uid) for uid in batch])
        
        # Atualizar progresso
        progress = min(i + batch_size, total)
        try:
            await status_msg.edit_text(
                f"📤 Enviando... {progress}/{total}\n"
                f"✅ {sent} | ❌ {failed}"
            )
        except:
            pass
    
    # Resultado final
    await status_msg.edit_text(
        f"✅ **BROADCAST CONCLUÍDO**\n\n"
        f"📊 Total: {total}\n"
        f"✅ Enviados: {sent}\n"
        f"❌ Falhas: {failed}\n"
        f"⚡ Taxa: {sent/(total/20):.1f}x mais rápido",
        parse_mode="Markdown"
    )

async def send_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /send <user_id> <mensagem>")
        return
    
    try:
        uid = int(context.args[0])
        message = " ".join(context.args[1:])
        
        await context.bot.send_message(chat_id=uid, text=message)
        await update.message.reply_text(f"✅ Mensagem enviada para {uid}")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def sendphoto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text(
            "📸 **Como usar:**\n\n"
            "1️⃣ Envie uma foto ou documento\n"
            "2️⃣ Responda com `/sendphoto <user_id> [legenda]`\n\n"
            "Exemplo: `/sendphoto 123456789 Olha isso! 💕`",
            parse_mode="Markdown"
        )
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Responda a uma foto ou documento com este comando")
        return
    
    reply = update.message.reply_to_message
    
    try:
        uid = int(context.args[0])
        caption = " ".join(context.args[1:]) if len(context.args) > 1 else None
        
        if reply.photo:
            await context.bot.send_photo(
                chat_id=uid,
                photo=reply.photo[-1].file_id,
                caption=caption
            )
            await update.message.reply_text(f"✅ Foto enviada para {uid}")
        
        elif reply.document:
            await context.bot.send_document(
                chat_id=uid,
                document=reply.document.file_id,
                caption=caption
            )
            await update.message.reply_text(f"✅ Documento enviado para {uid}")
        
        elif reply.video:
            await context.bot.send_video(
                chat_id=uid,
                video=reply.video.file_id,
                caption=caption
            )
            await update.message.reply_text(f"✅ Vídeo enviado para {uid}")
        
        elif reply.audio:
            await context.bot.send_audio(
                chat_id=uid,
                audio=reply.audio.file_id,
                caption=caption
            )
            await update.message.reply_text(f"✅ Áudio enviado para {uid}")
        
        elif reply.voice:
            await context.bot.send_voice(
                chat_id=uid,
                voice=reply.voice.file_id,
                caption=caption
            )
            await update.message.reply_text(f"✅ Mensagem de voz enviada para {uid}")
        
        elif reply.video_note:
            await context.bot.send_video_note(
                chat_id=uid,
                video_note=reply.video_note.file_id
            )
            await update.message.reply_text(f"✅ Video note enviado para {uid}")
        
        elif reply.sticker:
            await context.bot.send_sticker(
                chat_id=uid,
                sticker=reply.sticker.file_id
            )
            await update.message.reply_text(f"✅ Sticker enviado para {uid}")
        
        else:
            await update.message.reply_text("❌ Tipo de mídia não suportado. Use foto, documento, vídeo ou áudio.")
            
    except ValueError:
        await update.message.reply_text("❌ ID de usuário inválido")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")

async def migrate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    await update.message.reply_text("🔄 Migrando...")
    
    migrated = 0
    all_uids = set()
    
    for key in r.keys("memory:*"):
        uid = key.replace("memory:", "")
        if uid.isdigit():
            all_uids.add(uid)
    
    for key in r.keys("lang:*"):
        uid = key.replace("lang:", "")
        if uid.isdigit():
            all_uids.add(uid)
    
    for uid in all_uids:
        r.sadd(all_users_key(), uid)
        if not r.exists(last_activity_key(int(uid))):
            r.set(last_activity_key(int(uid)), (datetime.now() - timedelta(hours=25)).isoformat())
        migrated += 1
    
    await update.message.reply_text(f"✅ {migrated} usuários migrados")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if update.effective_user.id in ADMIN_IDS and context.args:
        uid = int(context.args[0])
    
    streak = get_streak(uid)
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    vip_status = is_vip(uid)
    vip_expiry = get_vip_expiry(uid)
    ignored = get_ignored_count(uid)
    paused = is_engagement_paused(uid)
    
    msg = f"📋 **STATUS**\n\n"
    msg += f"👤 ID: `{uid}`\n"
    msg += f"🔥 Streak: {streak} dias\n"
    msg += f"💬 Msgs hoje: {count}/{LIMITE_DIARIO}\n"
    if bonus > 0:
        msg += f"🎁 Msgs bônus: {bonus}\n"
    
    if vip_status:
        msg += f"💎 VIP: ✅ (até {vip_expiry.strftime('%d/%m/%Y')})\n"
    else:
        msg += f"💎 VIP: ❌\n"
        msg += f"📊 Restam: {max(0, LIMITE_DIARIO + bonus - count)} msgs\n"
    
    msg += f"\n🔔 **Engajamento:**\n"
    msg += f"• Ignorou: {ignored}/3\n"
    msg += f"• Pausado: {'⏸️ Sim' if paused else '▶️ Não'}"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def viplist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    users = get_all_active_users()
    vips = []
    
    for uid in users:
        if is_vip(uid):
            expiry = get_vip_expiry(uid)
            vips.append((uid, expiry))
    
    if not vips:
        await update.message.reply_text("Nenhum VIP ativo")
        return
    
    msg = "💎 **VIPs ATIVOS**\n\n"
    for uid, expiry in sorted(vips, key=lambda x: x[1]):
        msg += f"• `{uid}` → até {expiry.strftime('%d/%m/%Y')}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def userinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /userinfo <user_id>")
        return
    
    uid = int(context.args[0])
    
    profile = get_user_profile(uid)
    streak = get_streak(uid)
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    vip_status = is_vip(uid)
    vip_expiry = get_vip_expiry(uid)
    last_activity = get_last_activity(uid)
    funnel_stage = int(r.get(funnel_key(uid)) or 0)
    memory_count = len(get_memory(uid))
    ignored = get_ignored_count(uid)
    paused = is_engagement_paused(uid)
    onboard_choice = get_onboarding_choice(uid)  # [NOVO v6]
    
    msg = f"👤 **USUÁRIO {uid}**\n\n"
    msg += f"📝 Nome: {profile.get('name', 'N/A')}\n"
    msg += f"🎂 Idade: {profile.get('age', 'N/A')}\n"
    msg += f"🎯 Onboarding: {onboard_choice or 'N/A'}\n"  # [NOVO v6]
    msg += f"🔥 Streak: {streak} dias\n"
    msg += f"💬 Msgs hoje: {count}/{LIMITE_DIARIO}\n"
    msg += f"🎁 Bônus: {bonus}\n"
    msg += f"🧠 Memória: {memory_count} msgs\n"
    msg += f"📊 Funil: {funnel_stage}/9\n"
    
    if vip_status:
        msg += f"💎 VIP: ✅ até {vip_expiry.strftime('%d/%m/%Y')}\n"
    else:
        msg += f"💎 VIP: ❌\n"
    
    if last_activity:
        hours_ago = (datetime.now() - last_activity).total_seconds() / 3600
        msg += f"⏰ Última atividade: {hours_ago:.1f}h atrás\n"
    
    msg += f"\n🔔 **Engajamento:**\n"
    msg += f"• Ignorou: {ignored}/3\n"
    msg += f"• Pausado: {'⏸️ Sim' if paused else '▶️ Não'}\n"
    
    if is_blacklisted(uid):
        msg += f"\n🚫 BLOQUEADO\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def givebonus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /givebonus <user_id> <quantidade>")
        return
    
    uid = int(context.args[0])
    amount = int(context.args[1])
    
    add_bonus_msgs(uid, amount)
    await update.message.reply_text(f"✅ +{amount} msgs bônus para {uid}\n(Total: {get_bonus_msgs(uid)})")
    
    try:
        await context.bot.send_message(
            uid, f"🎁 Você ganhou +{amount} mensagens extras! Aproveite 💕"
        )
    except:
        pass

async def blacklist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /blacklist <user_id>")
        return
    
    uid = int(context.args[0])
    add_to_blacklist(uid)
    await update.message.reply_text(f"🚫 Usuário {uid} bloqueado")

async def unblacklist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /unblacklist <user_id>")
        return
    
    uid = int(context.args[0])
    remove_from_blacklist(uid)
    await update.message.reply_text(f"✅ Usuário {uid} desbloqueado")

async def unpause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /unpause <user_id>")
        return
    
    uid = int(context.args[0])
    unpause_engagement(uid)
    await update.message.reply_text(f"▶️ Gatilhos reativados para {uid}")

async def pausedlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    users = get_all_active_users()
    paused_users = []
    
    for uid in users:
        if is_engagement_paused(uid):
            paused_users.append(uid)
    
    if not paused_users:
        await update.message.reply_text("Nenhum usuário com gatilhos pausados")
        return
    
    msg = f"⏸️ **USUÁRIOS PAUSADOS** ({len(paused_users)})\n\n"
    for uid in paused_users[:50]:
        msg += f"• `{uid}`\n"
    
    if len(paused_users) > 50:
        msg += f"\n... e mais {len(paused_users) - 50}"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

# ================= CONFIGURAÇÃO DO BOT =================
def setup_application():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Comandos usuário
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("status", status_cmd))
    
    # Comandos admin
    application.add_handler(CommandHandler("reset", reset_cmd))
    application.add_handler(CommandHandler("resetall", resetall_cmd))
    application.add_handler(CommandHandler("clearmemory", clearmemory_cmd))
    application.add_handler(CommandHandler("setvip", setvip_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("funnel", funnel_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    application.add_handler(CommandHandler("send", send_cmd))
    application.add_handler(CommandHandler("sendphoto", sendphoto_cmd))
    application.add_handler(CommandHandler("migrate", migrate_cmd))
    application.add_handler(CommandHandler("viplist", viplist_cmd))
    application.add_handler(CommandHandler("userinfo", userinfo_cmd))
    application.add_handler(CommandHandler("givebonus", givebonus_cmd))
    application.add_handler(CommandHandler("blacklist", blacklist_cmd))
    application.add_handler(CommandHandler("unblacklist", unblacklist_cmd))
    application.add_handler(CommandHandler("unpause", unpause_cmd))
    application.add_handler(CommandHandler("pausedlist", pausedlist_cmd))
    
    # Handlers
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

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def start_loop():
    loop.run_forever()

import threading
threading.Thread(target=start_loop, daemon=True).start()

scheduler_started = False

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route("/set-webhook", methods=["GET"])
def set_webhook_route():
    asyncio.run_coroutine_threadsafe(setup_webhook(), loop)
    return "Webhook configurado", 200

@app.route("/trigger-engagement", methods=["GET"])
def trigger_engagement():
    asyncio.run_coroutine_threadsafe(process_engagement_jobs(application.bot), loop)
    return "Jobs disparados", 200

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    try:
        data = request.json
        if not data:
            return "ok", 200
        update = Update.de_json(data, application.bot)
        asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
        return "ok", 200
    except Exception as e:
        logger.exception(f"Erro webhook: {e}")
        return "error", 500

async def setup_webhook():
    global scheduler_started
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook: {webhook_url}")
        
        if not scheduler_started:
            asyncio.create_task(engagement_scheduler(application.bot))
            scheduler_started = True
    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        
adicionar_rota_webhook(app, application, loop)

if __name__ == "__main__":
    asyncio.run_coroutine_threadsafe(application.initialize(), loop)
    asyncio.run_coroutine_threadsafe(application.start(), loop)
    asyncio.run_coroutine_threadsafe(engagement_scheduler(application.bot), loop)
    logger.info(f"🌐 Flask porta {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
