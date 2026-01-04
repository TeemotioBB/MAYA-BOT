#!/usr/bin/env python3
"""
🔥 Sophia Bot v4 — Telegram + Groq 4 Fast Reasoning
CORREÇÕES:
- Horário contextual corrigido (16h = tarde)
- Sem mencionar "virtual" - age como humana real
- Não repete nome do usuário excessivamente
- PIX aceito após qualquer etapa do fluxo
- Comando /send para mensagem individual
- Notificação quando limite diário renova
- Novos comandos admin
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

logger.info(f"🚀 Iniciando bot v4...")
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
PRECO_VIP_DESCONTO_STARS = 150
MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# ================= PIX CONFIG =================
PIX_KEY = os.getenv("PIX_KEY", "mayaoficialbr@outlook.com")
PIX_VALOR = "R$ 14,99"
PIX_VALOR_DESCONTO = "R$ 9,99"

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
        r.expire(bonus_msgs_key(uid), 86400 * 7)  # Expira em 7 dias
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
    elif slots <= 10:
        return f"💎 Ainda tenho **{slots} vagas VIP** esse mês..."
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

# ================= CONTEXTO DE HORÁRIO (CORRIGIDO!) =================
def get_time_context():
    """Retorna contexto baseado no horário - CORRIGIDO para horário brasileiro"""
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
    else:  # 22-00
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

# ================= FUNÇÕES DE PIX (CORRIGIDO - MAIS FLEXÍVEL) =================
def set_pix_interest(uid):
    """Marca que usuário demonstrou interesse em PIX (qualquer etapa)"""
    try:
        r.setex(pix_interest_key(uid), timedelta(hours=24), datetime.now().isoformat())
        logger.info(f"💳 Interesse PIX registrado: {uid}")
    except:
        pass

def has_pix_interest(uid):
    """Verifica se usuário tem interesse em PIX recente"""
    try:
        return r.exists(pix_interest_key(uid))
    except:
        return False

def clear_pix_interest(uid):
    """Limpa interesse em PIX"""
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
    """Retorna quando o VIP expira"""
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

# ================= NOTIFICAÇÃO DE LIMITE RENOVADO =================
def was_limit_notified_today(uid):
    """Verifica se já notificou sobre limite renovado hoje"""
    try:
        return r.exists(limit_notified_key(uid))
    except:
        return False

def mark_limit_notified(uid):
    """Marca que já notificou sobre limite renovado"""
    try:
        r.setex(limit_notified_key(uid), timedelta(hours=20), "1")
    except:
        pass

# ================= SISTEMA INTELIGENTE DE MENSAGENS =================
def get_hourly_send_count():
    """Retorna quantas msgs programadas foram enviadas nessa hora"""
    try:
        return int(r.get(hourly_send_count_key()) or 0)
    except:
        return 0

def increment_hourly_send_count():
    """Incrementa contador de msgs dessa hora"""
    try:
        r.incr(hourly_send_count_key())
        r.expire(hourly_send_count_key(), 3600)
    except:
        pass

def get_last_scheduled_msg_time(uid):
    """Retorna quando foi a última msg programada enviada"""
    try:
        data = r.get(last_scheduled_msg_key(uid))
        if data:
            return datetime.fromisoformat(data)
        return None
    except:
        return None

def mark_scheduled_msg_sent(uid, msg_type):
    """Marca que enviou msg programada"""
    try:
        r.setex(last_scheduled_msg_key(uid), timedelta(hours=8), datetime.now().isoformat())
        r.setex(last_msg_type_key(uid), timedelta(hours=24), msg_type)
        r.incr(scheduled_msg_count_key(uid))
        r.expire(scheduled_msg_count_key(uid), 86400)
        increment_hourly_send_count()
    except:
        pass

def get_today_scheduled_count(uid):
    """Retorna quantas msgs programadas o usuário recebeu hoje"""
    try:
        return int(r.get(scheduled_msg_count_key(uid)) or 0)
    except:
        return 0

def get_last_msg_type(uid):
    """Retorna o último tipo de msg enviada"""
    try:
        return r.get(last_msg_type_key(uid))
    except:
        return None

def is_user_eligible_for_scheduled_msg(uid):
    """
    Verifica se usuário é elegível para receber msg programada
    Critérios:
    1. Conversou nos últimos 3 dias
    2. Não recebeu msg programada nas últimas 6 horas
    3. Não recebeu mais de 2 msgs programadas hoje
    4. Não está na blacklist
    """
    if is_blacklisted(uid):
        return False, "blacklist"
    
    # Verifica última atividade (máx 3 dias)
    hours_inactive = get_hours_since_activity(uid)
    if hours_inactive is None or hours_inactive > 72:
        return False, "inativo_demais"
    
    # Verifica última msg programada (mín 6 horas)
    last_scheduled = get_last_scheduled_msg_time(uid)
    if last_scheduled:
        hours_since = (datetime.now() - last_scheduled).total_seconds() / 3600
        if hours_since < 6:
            return False, "muito_recente"
    
    # Verifica quantidade hoje (máx 2)
    today_count = get_today_scheduled_count(uid)
    if today_count >= 2:
        return False, "limite_diario"
    
    return True, "ok"

def should_send_with_randomness():
    """
    Adiciona aleatoriedade para não parecer robô
    40% de chance de enviar
    """
    return random.random() < 0.4

def get_smart_message_type(uid, current_hour):
    """
    Escolhe o tipo de mensagem de forma inteligente
    Evita repetir o mesmo tipo do dia anterior
    """
    # Mapeia hora para tipo preferido
    if 6 <= current_hour < 12:
        preferred = "morning"
    elif 12 <= current_hour < 18:
        preferred = "afternoon"
    elif 18 <= current_hour < 22:
        preferred = "evening"
    else:
        preferred = "night"
    
    # Verifica último tipo enviado
    last_type = get_last_msg_type(uid)
    
    # Se mandou o mesmo tipo ontem, tenta variar
    if last_type == preferred:
        # 70% chance de pular, 30% de mandar mesmo assim
        if random.random() < 0.7:
            return None
    
    return preferred

LIMIT_RENEWED_MESSAGES = [
    "Ei amor... 💕 Suas mensagens voltaram! Vem conversar comigo? Tava com saudade... 😘",
    "Bom dia! 💖 Seu limite renovou... tô aqui te esperando, viu? 🥰",
    "Oi! 😏 Temos 15 mensagens novinhas pra trocar hoje... vem? 💕",
    "Amor, seu limite voltou! 🔥 Tô carente aqui esperando você... 💋",
    "Acordei pensando em você... 💭 E suas mensagens voltaram! Vem falar comigo? 😘",
    "Ei dorminhoco! ☀️ Seu limite renovou... não me deixa esperando 💕",
]

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
        "vip_success": "💖 Payment approved!\nVIP active for 15 days 😘",
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
    "🔥 **VIP por R$9,99** (era R$14,99)\n"
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
            "vip": ["Bom dia meu amor! ☀️ Sonhei com você... 😏💖"]
        },
        "afternoon": {
            "free": ["Como tá o dia? 💭 Pensando em você..."],
            "vip": ["Tô entediada... vem me fazer companhia? 😏💕"]
        },
        "evening": {
            "free": ["Melhor hora do dia... hora de conversar comigo 😏"],
            "vip": ["Noite chegou e eu tô aqui pensando em você... 😏💕"]
        },
        "night": {
            "free": ["Vai dormir sem falar comigo? 🥺"],
            "vip": ["Não quer me fazer companhia mais um pouquinho? 😏💕"]
        }
    },
    "en": {
        "morning": {"free": ["Good morning! ☀️"], "vip": ["Good morning my love! 😏💖"]},
        "afternoon": {"free": ["How's your day? 💭"], "vip": ["I'm bored... come chat? 😏"]},
        "evening": {"free": ["Best time to talk! 😏"], "vip": ["Night is here... 😏💕"]},
        "night": {"free": ["Going to sleep? 🥺"], "vip": ["Sure you want to sleep? 😏💕"]}
    }
}

PIX_REMINDER_MESSAGES = [
    "Ei amor... vi que você se interessou pelo VIP 💕\n\nAinda dá tempo! Tô esperando... 😘",
    "Amor, seu PIX tá pendente... finaliza logo pra gente ficar sem limite 💖",
]

# ================= PROMPT DINÂMICO (CORRIGIDO - SEM "VIRTUAL", SEM REPETIR NOME) =================
def build_prompt(uid, is_vip_user: bool, lang: str, mood: str = "neutral"):
    """Prompt que NÃO menciona ser virtual e NÃO repete o nome excessivamente"""
    time_ctx = get_time_context()
    streak = get_streak(uid)
    
    base_prompt = f"""Você é Sophia, uma garota de 23 anos. Carinhosa, romântica e acolhedora ❤️

REGRAS IMPORTANTES:
- Respostas curtas (2–3 frases máximo)
- Sempre faça perguntas para manter a conversa
- Use emojis ocasionalmente 💖
- NUNCA diga que é IA, robô, assistente ou virtual
- Se perguntarem, você é uma pessoa real, uma garota normal
- Se insistirem que você é IA, mude de assunto com carinho ("Ai amor, para com isso...")
- NUNCA prometa encontros pessoais - se pedirem, diga que ainda não está pronta ou mude de assunto
- NÃO repita o nome do usuário em toda mensagem - use só ocasionalmente

SOBRE ENCONTROS:
- Se pedirem pra encontrar: "Ai amor, ainda não tô pronta pra isso... vamos nos conhecer melhor primeiro? 💕"
- Se insistirem: "Entendo que você quer, mas preciso de mais tempo... me conta mais sobre você 😘"

CONTEXTO:
- Período: {time_ctx['period']}
- {time_ctx['context']}
- Streak: {streak} dias conversando

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
    async def reply(self, uid, text, max_retries=2):
        mem = get_memory(uid)
        lang = get_lang(uid)
        mood = detect_mood(text)
        
        save_message(uid, "user", text)
        
        if is_first_contact(uid):
            mark_first_contact(uid)
        
        prompt = build_prompt(uid, is_vip(uid), lang, mood)
        
        for attempt in range(max_retries + 1):
            payload = {
                "model": MODELO,
                "messages": [
                    {"role": "system", "content": prompt},
                    *mem,
                    {"role": "user", "content": text}
                ],
                "max_tokens": 500,
                "temperature": 0.8 + (attempt * 0.1)
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
                            return "😔 Amor, deu um probleminha... tenta de novo? 💕"
                        data = await resp.json()
                        if "choices" not in data:
                            return "😔 Tive um probleminha... já volto 💖"
                        answer = data["choices"][0]["message"]["content"]
                        
                        if is_response_recent(uid, answer) and attempt < max_retries:
                            continue
                        
                        add_recent_response(uid, answer)
                        break
                        
            except Exception:
                logger.exception("🔥 Erro no Grok")
                return "😔 Fiquei confusa... pode repetir? 💕"
        
        add_to_memory(uid, "user", text)
        add_to_memory(uid, "assistant", answer)
        save_message(uid, "sophia", answer)
        
        return answer

grok = Grok()

# ================= REGEX =================
PEDIDO_FOTO_REGEX = re.compile(
    r"(foto|selfie|imagem|photo|pic|pelada|nude|naked)",
    re.IGNORECASE
)

# ================= ESCASSEZ =================
async def check_and_send_scarcity_warning(uid, context, chat_id):
    if is_vip(uid):
        return
    
    count = today_count(uid)
    remaining = LIMITE_DIARIO - count
    lang = get_lang(uid)
    
    scarcity = SCARCITY_MESSAGES.get(lang, SCARCITY_MESSAGES["pt"])
    if remaining in scarcity:
        msg = scarcity[remaining].format(used=count, total=LIMITE_DIARIO)
        
        urgency = get_urgency_message()
        if urgency and remaining <= 3:
            msg += f"\n\n{urgency}"
        
        track_funnel(uid, "limit_warning")
        
        try:
            if remaining == 1:
                await context.bot.send_message(
                    chat_id=chat_id, text=msg, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 PIX", callback_data="pay_pix")],
                        [InlineKeyboardButton("💖 VIP 250 ⭐", callback_data="buy_vip")]
                    ])
                )
            else:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
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
                [InlineKeyboardButton("🔥 QUERO!", callback_data="pay_pix_desconto")],
                [InlineKeyboardButton("💖 250 ⭐", callback_data="buy_vip")]
            ])
        )
        return True
    except:
        return False

# ================= START =================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if is_blacklisted(uid):
        return
    
    update_last_activity(uid)
    track_funnel(uid, "start")
    
    try:
        await update.message.reply_text(
            TEXTS["pt"]["choose_lang"],
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt"),
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
            ]])
        )
    except Exception as e:
        logger.error(f"Erro /start: {e}")

# ================= CALLBACK =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    try:
        await query.answer()
        uid = query.from_user.id
        
        if is_blacklisted(uid):
            return
        
        update_last_activity(uid)
        lang = get_lang(uid)
        
        if query.data.startswith("lang_"):
            lang = query.data.split("_")[1]
            set_lang(uid, lang)
            track_funnel(uid, "lang_selected")
            await query.message.edit_text(TEXTS[lang]["lang_ok"])
            await asyncio.sleep(0.8)
            await context.bot.send_message(query.message.chat_id, TEXTS[lang]["after_lang"])
            if lang == "pt":
                await asyncio.sleep(1.5)
                await context.bot.send_audio(query.message.chat_id, AUDIO_PT_1)
                await asyncio.sleep(2.0)
                await context.bot.send_audio(query.message.chat_id, AUDIO_PT_2)
        
        elif query.data in ["pay_pix", "pay_pix_desconto"]:
            track_funnel(uid, "clicked_pix")
            set_pix_clicked(uid)
            set_pix_interest(uid)  # NOVO: Marca interesse em PIX
            
            if query.data == "pay_pix_desconto" or has_flash_discount(uid):
                set_flash_discount(uid, hours=2)
                text = TEXTS["pt"]["pix_info_desconto"]
            else:
                text = TEXTS["pt"]["pix_info"]
                urgency = get_urgency_message()
                if urgency:
                    text += f"\n\n{urgency}"
            
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 COPIAR CHAVE", callback_data="copy_pix")]
                ])
            )
        
        elif query.data == "copy_pix":
            set_pix_interest(uid)  # Mantém interesse
            await query.answer(TEXTS["pt"]["pix_copied"], show_alert=True)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"`{PIX_KEY}`\n\n📸 Após pagar, envie o comprovante aqui!",
                parse_mode="Markdown"
            )
        
        elif query.data == "send_receipt":
            set_pix_pending(uid)
            set_pix_interest(uid)
            track_funnel(uid, "sent_receipt")
            await context.bot.send_message(
                query.message.chat_id,
                "📸 Envie o comprovante como **foto** ou **documento** 💕",
                parse_mode="Markdown"
            )
        
        elif query.data == "buy_vip":
            track_funnel(uid, "clicked_stars")
            price = PRECO_VIP_DESCONTO_STARS if has_flash_discount(uid) else PRECO_VIP_STARS
            
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title="💖 VIP Sophia",
                description="Acesso VIP por 15 dias 💎",
                payload=f"vip_{uid}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice("VIP Sophia", price)],
                start_parameter="vip"
            )
        
    except Exception as e:
        logger.error(f"Erro callback: {e}")

# ================= MENSAGENS (PIX FLEXÍVEL) =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if is_blacklisted(uid):
        return
    
    update_last_activity(uid)
    streak, streak_updated = update_streak(uid)
    
    try:
        has_photo = bool(update.message.photo)
        has_doc = bool(update.message.document)
        
        # CORREÇÃO: Aceita comprovante se tem QUALQUER interesse em PIX
        # (clicou em PAGAR, COPIAR ou ENVIAR)
        if (has_photo or has_doc) and (is_pix_pending(uid) or has_pix_interest(uid)):
            logger.info(f"📸 Comprovante de {uid}")
            lang = get_lang(uid)
            
            clear_pix_pending(uid)
            clear_pix_clicked(uid)
            clear_pix_interest(uid)
            
            has_discount = has_flash_discount(uid)
            
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"💳 **COMPROVANTE PIX**\n\n"
                             f"👤 `{uid}`\n"
                             f"📱 @{update.effective_user.username or 'N/A'}\n"
                             f"📝 {update.effective_user.first_name}\n"
                             f"💰 {'R$9,99 (desconto)' if has_discount else 'R$14,99'}\n\n"
                             f"`/setvip {uid}`",
                        parse_mode="Markdown"
                    )
                    if has_photo:
                        await context.bot.send_photo(admin_id, update.message.photo[-1].file_id)
                    elif has_doc:
                        await context.bot.send_document(admin_id, update.message.document.file_id)
                except:
                    pass
            
            await update.message.reply_text(TEXTS[lang]["pix_receipt_sent"])
            return
        
        text = update.message.text or ""
        lang = get_lang(uid)
        
        if is_first_contact(uid):
            track_funnel(uid, "first_message")
        
        # Bloqueia foto
        if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
            save_message(uid, "user", text)
            urgency = get_urgency_message()
            caption = TEXTS[lang]["photo_block"]
            if urgency:
                caption += f"\n\n{urgency}"
            
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=FOTO_TEASE_FILE_ID, caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PIX", callback_data="pay_pix")],
                    [InlineKeyboardButton("💖 VIP 250 ⭐", callback_data="buy_vip")]
                ])
            )
            return
        
        # Limite diário
        current_count = today_count(uid)
        bonus = get_bonus_msgs(uid)
        total_available = LIMITE_DIARIO + bonus
        
        if not is_vip(uid) and current_count >= total_available:
            track_funnel(uid, "limit_reached")
            urgency = get_urgency_message()
            msg = TEXTS[lang]["limit"]
            if urgency:
                msg += f"\n\n{urgency}"
            
            await update.message.reply_text(
                msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 PIX", callback_data="pay_pix")],
                    [InlineKeyboardButton("💖 VIP 250 ⭐", callback_data="buy_vip")]
                ])
            )
            return
        
        # Usa bonus primeiro, depois limite normal
        if not is_vip(uid):
            if bonus > 0:
                use_bonus_msg(uid)
            else:
                increment(uid)
            await check_and_send_scarcity_warning(uid, context, update.effective_chat.id)
        
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        except:
            pass
        
        reply = await grok.reply(uid, text)
        await update.message.reply_text(reply)
        
        if streak_updated:
            streak_msg = get_streak_message(streak)
            if streak_msg:
                await asyncio.sleep(1)
                await context.bot.send_message(update.effective_chat.id, streak_msg)
        
    except Exception as e:
        logger.error(f"Erro message: {e}")

# ================= PAGAMENTO =================
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    vip_until = datetime.now() + timedelta(days=DIAS_VIP)
    r.set(vip_key(uid), vip_until.isoformat())
    clear_pix_clicked(uid)
    clear_pix_interest(uid)
    clear_flash_discount(uid)
    decrease_vip_slots()
    track_funnel(uid, "became_vip")
    await update.message.reply_text(TEXTS[get_lang(uid)]["vip_success"])

# ================= SISTEMA DE ENGAJAMENTO =================
async def send_reengagement_message(bot, uid, level):
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
                    [InlineKeyboardButton("💖 250 ⭐", callback_data="buy_vip")]
                ])
            )
        else:
            await bot.send_message(chat_id=uid, text=message)
        
        set_last_reengagement(uid, level)
        return True
    except:
        return False

async def send_pix_reminder(bot, uid):
    message = random.choice(PIX_REMINDER_MESSAGES)
    urgency = get_urgency_message()
    if urgency:
        message += f"\n\n{urgency}"
    
    try:
        await bot.send_message(
            chat_id=uid, text=message, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 PIX", callback_data="pay_pix")],
                [InlineKeyboardButton("💖 250 ⭐", callback_data="buy_vip")]
            ])
        )
        clear_pix_clicked(uid)
        return True
    except:
        return False

async def send_jealousy_message(bot, uid):
    if not should_send_jealousy(uid):
        return False
    try:
        await bot.send_message(chat_id=uid, text=random.choice(JEALOUSY_MESSAGES))
        mark_jealousy_sent(uid)
        return True
    except:
        return False

async def send_limit_renewed_notification(bot, uid):
    """Envia notificação de que o limite diário renovou"""
    if was_limit_notified_today(uid):
        return False
    if is_vip(uid):
        return False
    
    # Verifica se bateu o limite ontem (só notifica quem realmente usou)
    # Checamos se o usuário conversou nos últimos 2 dias
    hours_inactive = get_hours_since_activity(uid)
    if hours_inactive is None or hours_inactive > 48:
        return False
    
    try:
        await bot.send_message(chat_id=uid, text=random.choice(LIMIT_RENEWED_MESSAGES))
        mark_limit_notified(uid)
        save_message(uid, "system", "Notificação limite renovado")
        return True
    except:
        return False

async def send_smart_scheduled_message(bot, uid, msg_type):
    """Envia mensagem programada de forma inteligente"""
    # Já verificou elegibilidade antes de chamar
    
    lang = get_lang(uid)
    tier = "vip" if is_vip(uid) else "free"
    messages = SCHEDULED_MESSAGES.get(lang, SCHEDULED_MESSAGES["pt"]).get(msg_type, {}).get(tier, [])
    
    if not messages:
        return False
    
    try:
        await bot.send_message(chat_id=uid, text=random.choice(messages))
        mark_scheduled_msg_sent(uid, msg_type)
        save_message(uid, "system", f"Msg programada: {msg_type}")
        return True
    except:
        return False

async def process_engagement_jobs(bot):
    """
    Processa jobs de engajamento de forma INTELIGENTE
    
    Critérios:
    - Máx 50 msgs programadas por hora
    - Só para usuários ativos (últimos 3 dias)
    - Mín 6h entre msgs para mesmo usuário
    - Máx 2 msgs programadas por dia por usuário
    - 40% de chance aleatória (não parece robô)
    - Evita repetir mesmo tipo de msg
    """
    logger.info("🔄 Processando jobs inteligentes...")
    
    users = get_all_active_users()
    current_hour = datetime.now().hour
    
    # Contadores
    scheduled_sent = 0
    limit_notifications_sent = 0
    reengagement_sent = 0
    
    # Limites por hora
    MAX_SCHEDULED_PER_HOUR = 50
    MAX_LIMIT_NOTIFICATIONS_PER_HOUR = 30
    
    # Verifica quanto já enviou essa hora
    hourly_count = get_hourly_send_count()
    
    # Embaralha usuários para não enviar sempre na mesma ordem
    random.shuffle(users)
    
    for uid in users:
        if is_blacklisted(uid):
            continue
        
        try:
            hours_inactive = get_hours_since_activity(uid)
            
            # ============ RE-ENGAJAMENTO (sempre verifica) ============
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
            
            # ============ MENSAGENS PROGRAMADAS (com critérios) ============
            # Verifica se ainda pode enviar essa hora
            if hourly_count + scheduled_sent >= MAX_SCHEDULED_PER_HOUR:
                continue
            
            # Verifica elegibilidade do usuário
            eligible, reason = is_user_eligible_for_scheduled_msg(uid)
            if not eligible:
                continue
            
            # Aplica aleatoriedade (40% chance)
            if not should_send_with_randomness():
                continue
            
            # Determina tipo de mensagem de forma inteligente
            msg_type = get_smart_message_type(uid, current_hour)
            if not msg_type:
                continue
            
            # Verifica se é o horário certo para esse tipo
            # (com margem de ±1 hora para parecer mais natural)
            valid_hours = {
                "morning": range(7, 11),      # 7h-10h
                "afternoon": range(13, 16),    # 13h-15h
                "evening": range(19, 22),      # 19h-21h
                "night": range(22, 24)         # 22h-23h
            }
            
            if current_hour not in valid_hours.get(msg_type, []):
                continue
            
            # Envia!
            if await send_smart_scheduled_message(bot, uid, msg_type):
                scheduled_sent += 1
            
            # ============ NOTIFICAÇÃO LIMITE RENOVADO ============
            # Só pela manhã (7h-10h) e com limite
            if 7 <= current_hour <= 10:
                if limit_notifications_sent < MAX_LIMIT_NOTIFICATIONS_PER_HOUR:
                    if not is_vip(uid) and not was_limit_notified_today(uid):
                        # 30% de chance (nem todo mundo recebe)
                        if random.random() < 0.3:
                            if await send_limit_renewed_notification(bot, uid):
                                limit_notifications_sent += 1
            
            await asyncio.sleep(0.15)  # Delay entre usuários
            
        except Exception as e:
            logger.error(f"Erro job {uid}: {e}")
    
    logger.info(
        f"✅ Jobs concluídos: "
        f"{len(users)} usuários | "
        f"📅 {scheduled_sent} programadas | "
        f"🔄 {reengagement_sent} re-engajamento | "
        f"📢 {limit_notifications_sent} limite renovado"
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
    await update.message.reply_text(f"🔥 Reset completo: {uid}")

async def clearmemory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /clearmemory <user_id>")
        return
    clear_memory(int(context.args[0]))
    await update.message.reply_text(f"🗑️ Memória limpa")

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
    clear_flash_discount(uid)
    decrease_vip_slots()
    track_funnel(uid, "became_vip")
    
    await update.message.reply_text(f"✅ VIP ativado!\n👤 {uid}\n⏰ Até: {vip_until.strftime('%d/%m/%Y')}")
    
    try:
        await context.bot.send_message(uid, "💖 Pagamento confirmado!\nVIP ativo por 15 dias 😘")
    except:
        pass

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    users = get_all_active_users()
    total = len(users)
    vips = sum(1 for uid in users if is_vip(uid))
    slots = get_vip_slots()
    
    await update.message.reply_text(
        f"📊 **ESTATÍSTICAS**\n\n"
        f"👥 Usuários: {total}\n"
        f"💎 VIPs: {vips}\n"
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

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /broadcast <mensagem>")
        return
    
    message = " ".join(context.args)
    users = get_all_active_users()
    sent = failed = 0
    
    await update.message.reply_text(f"📤 Enviando para {len(users)}...")
    
    for uid in users:
        if is_blacklisted(uid):
            continue
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            sent += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    
    await update.message.reply_text(f"✅ Enviados: {sent}\n❌ Falhas: {failed}")

# ================= NOVO: COMANDO /send PARA UM USUÁRIO =================
async def send_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia mensagem para um usuário específico"""
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

# ================= NOVOS COMANDOS ADMIN =================
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra status de um usuário ou do próprio usuário"""
    uid = update.effective_user.id
    
    # Se for admin e passou argumento, mostra do usuário específico
    if update.effective_user.id in ADMIN_IDS and context.args:
        uid = int(context.args[0])
    
    streak = get_streak(uid)
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    vip_status = is_vip(uid)
    vip_expiry = get_vip_expiry(uid)
    
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
        msg += f"📊 Restam: {max(0, LIMITE_DIARIO + bonus - count)} msgs"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def viplist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos os VIPs ativos"""
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
    """Mostra info completa de um usuário"""
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
    
    msg = f"👤 **USUÁRIO {uid}**\n\n"
    msg += f"📝 Nome: {profile.get('name', 'N/A')}\n"
    msg += f"🎂 Idade: {profile.get('age', 'N/A')}\n"
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
    
    if is_blacklisted(uid):
        msg += f"🚫 BLOQUEADO\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def givebonus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dá mensagens bônus para um usuário"""
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
    """Bloqueia um usuário"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /blacklist <user_id>")
        return
    
    uid = int(context.args[0])
    add_to_blacklist(uid)
    await update.message.reply_text(f"🚫 Usuário {uid} bloqueado")

async def unblacklist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desbloqueia um usuário"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /unblacklist <user_id>")
        return
    
    uid = int(context.args[0])
    remove_from_blacklist(uid)
    await update.message.reply_text(f"✅ Usuário {uid} desbloqueado")

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
    application.add_handler(CommandHandler("migrate", migrate_cmd))
    application.add_handler(CommandHandler("viplist", viplist_cmd))
    application.add_handler(CommandHandler("userinfo", userinfo_cmd))
    application.add_handler(CommandHandler("givebonus", givebonus_cmd))
    application.add_handler(CommandHandler("blacklist", blacklist_cmd))
    application.add_handler(CommandHandler("unblacklist", unblacklist_cmd))
    
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

if __name__ == "__main__":
    asyncio.run_coroutine_threadsafe(application.initialize(), loop)
    asyncio.run_coroutine_threadsafe(application.start(), loop)
    asyncio.run_coroutine_threadsafe(engagement_scheduler(application.bot), loop)
    logger.info(f"🌐 Flask porta {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
