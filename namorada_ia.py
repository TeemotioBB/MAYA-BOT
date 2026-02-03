#!/usr/bin/env python3
"""
🔥 Sophia Bot v7 — Estratégia Canal de Prévias
FUNIL: BOT → CANAL PRÉVIAS → CANAL VIP

NOVIDADES v7:
- Sistema de tracking para quem vai/volta do canal de prévias
- Estratégia diferenciada para leads que conheceram prévias mas não compraram
- Onboarding simplificado focado em levar pro canal
- Removido sistema de pagamento direto (PIX/Stars)
- Foco em conversão via canal de prévias
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application, MessageHandler, ContextTypes, filters,
    CallbackQueryHandler, CommandHandler
)

"""
═══════════════════════════════════════════════════════════════
⚙️ CONFIGURAÇÃO RÁPIDA - EDITE AS LINHAS ABAIXO:
═══════════════════════════════════════════════════════════════
"""

# 🔥 1. COLE AQUI O TOKEN DO SEU BOT DO TELEGRAM
BOT_TOKEN = "COLE_SEU_TOKEN_BOT_AQUI"

# 🔥 2. COLE AQUI SUA API KEY DO GROK (https://console.x.ai/)
GROK_KEY = "COLE_SUA_KEY_GROK_AQUI"

# 🔥 3. COLE AQUI O LINK DO SEU CANAL DE PRÉVIAS
# Como pegar: Abra o canal → Compartilhar → Copiar link de convite
LINK_CANAL_PREVIAS = "https://t.me/+COLE_SEU_LINK_AQUI"

# 🔥 3b. COLE AQUI O LINK DO SEU CANAL VIP (onde o usuário paga/compra)
LINK_CANAL_VIP = "https://t.me/+COLE_SEU_LINK_VIP_AQUI"

# 🔥 4. COLE AQUI SEU TELEGRAM ID (pra ser admin)
# Como pegar: Mande /start pro @userinfobot
MEU_TELEGRAM_ID = "1293602874"

# 🔥 5. URL DO SEU APP NO RAILWAY (opcional - só se usar webhook)
WEBHOOK_URL = "https://seu-app.railway.app"

"""
═══════════════════════════════════════════════════════════════
✅ Pronto! Agora é só fazer deploy no Railway
═══════════════════════════════════════════════════════════════
"""

# ================= LOG =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= ENV =================
# Usa os valores configurados no topo OU variáveis de ambiente (Railway)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or BOT_TOKEN
GROK_API_KEY = os.getenv("GROK_API_KEY") or GROK_KEY
REDIS_URL = os.getenv("REDIS_URL", "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241")
PORT = int(os.getenv("PORT", 8080))

# Corrige URL do webhook (adiciona https:// se não tiver)
webhook_url = os.getenv("WEBHOOK_BASE_URL") or WEBHOOK_URL
if not webhook_url.startswith("http"):
    webhook_url = f"https://{webhook_url}"
WEBHOOK_BASE_URL = webhook_url
WEBHOOK_PATH = "/telegram"

# Validação
if not TELEGRAM_TOKEN or "COLE_SEU" in TELEGRAM_TOKEN:
    raise RuntimeError("❌ Configure BOT_TOKEN no topo do arquivo")
if not GROK_API_KEY or "COLE_SUA" in GROK_API_KEY:
    raise RuntimeError("❌ Configure GROK_KEY no topo do arquivo")

# ================= ADMIN =================
ADMIN_IDS = set(map(int, os.getenv("ADMIN_IDS", MEU_TELEGRAM_ID).split(",")))

# ================= CANAIS =================
# Usa o valor configurado no topo OU variável de ambiente
CANAL_PREVIAS_LINK = os.getenv("CANAL_PREVIAS_LINK") or LINK_CANAL_PREVIAS
CANAL_PREVIAS_ID = os.getenv("CANAL_PREVIAS_ID", "@seu_canal_previas")  # Username do canal (opcional)

CANAL_VIP_LINK = os.getenv("CANAL_VIP_LINK") or LINK_CANAL_VIP

logger.info(f"🚀 Iniciando bot v7 (Estratégia Canal)...")
logger.info(f"📍 Webhook: {WEBHOOK_BASE_URL}{WEBHOOK_PATH}")
logger.info(f"📢 Canal Prévias: {CANAL_PREVIAS_LINK}")
logger.info(f"💎 Canal VIP: {CANAL_VIP_LINK}")

# ================= REDIS =================
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    logger.info("✅ Redis conectado")
except Exception as e:
    logger.error(f"❌ Redis erro: {e}")
    raise

# ================= CONFIG =================
LIMITE_DIARIO = 7
MODELO = "grok-4-fast-reasoning"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"


# ================= ÁUDIOS PT-BR =================
AUDIO_PT_1 = "CQACAgEAAxkBAAEDDXFpaYkigGDlcTzZxaJXFuWDj1Ow5gAC5QQAAiq7UUdXWpPNiiNd1jgE"
AUDIO_PT_2 = "CQACAgEAAxkBAAEDAAEmaVRmPJ5iuBOaXyukQ06Ui23TSokAAocGAAIZwaFGkIERRmRoPes4BA"

# ================= FOTOS =================
FOTO_ONBOARDING_START = "https://i.postimg.cc/qq4NtgYQ/E775DE63-5B33-4DBB-A65F-FDD851021569.jpg"
FOTO_TEASE_PREVIAS = "https://i.postimg.cc/qq4NtgYQ/E775DE63-5B33-4DBB-A65F-FDD851021569.jpg"
FOTO_LIMITE_ATINGIDO = "https://i.postimg.cc/gjmxwr5f/IMG-8507.jpg"

# ================= FOTOS VIP (quando user virar VIP via admin) =================
FOTOS_VIP_WELCOME = [
    "https://i.postimg.cc/T1fKyhFG/IMG-8691.jpg",
    "https://i.postimg.cc/4yPmpsk0/IMG-8692.jpg",
    "https://i.postimg.cc/90bryC5S/IMG-8696.jpg",
]

# ================= KEYWORDS HOT =================
HOT_KEYWORDS = [
    'pau', 'buceta', 'chupar', 'gozar', 'tesão', 'foder', 'transar',
    'punheta', 'siririca', 'safada', 'gostosa', 'pelada', 'nua',
    'chupeta', 'boquete', 'anal', 'cu', 'rola', 'pica', 'mama',
    'seios', 'peitos', 'bunda', 'xereca', 'meter', 'fuder', 'sexo',
    'excitado', 'excitada', 'molhada', 'duro', 'tesudo', 'tesuda'
]

# ================= KEYWORDS CANAL/VIP =================
CANAL_TRIGGER_KEYWORDS = [
    'vip', 'premium', 'ilimitado', 'ilimitada', 'sem limite',
    'quanto custa', 'preço', 'pagar', 'pagamento', 'comprar',
    'quanto é', 'quanto ta', 'quanto tá', 'valor', 'plano',
    'assinatura', 'canal', 'grupo', 'previas', 'prévia'
]

# ================= MEMÓRIA PERSISTENTE =================
MAX_MEMORIA = 12

def memory_key(uid):
    return f"memory:{uid}"

def get_memory(uid):
    try:
        data = r.get(memory_key(uid))
        if data:
            return json.loads(data)
        return []
    except:
        return []

def save_memory(uid, messages):
    try:
        recent = messages[-MAX_MEMORIA:] if len(messages) > MAX_MEMORIA else messages
        r.setex(memory_key(uid), timedelta(days=7), json.dumps(recent, ensure_ascii=False))
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
def chatlog_key(uid): return f"chatlog:{uid}"
def last_activity_key(uid): return f"last_activity:{uid}"
def last_reengagement_key(uid): return f"last_reengagement:{uid}"
def daily_messages_sent_key(uid): return f"daily_msg_sent:{uid}:{date.today()}"
def all_users_key(): return "all_users"
def streak_key(uid): return f"streak:{uid}"
def streak_last_day_key(uid): return f"streak_last:{uid}"
def first_contact_key(uid): return f"first_contact:{uid}"
def user_profile_key(uid): return f"profile:{uid}"
def recent_responses_key(uid): return f"recent_resp:{uid}"
def funnel_key(uid): return f"funnel:{uid}"
def bonus_msgs_key(uid): return f"bonus:{uid}"
def blacklist_key(): return "blacklist"
def limit_notified_key(uid): return f"limit_notified:{uid}:{date.today()}"
def last_scheduled_msg_key(uid): return f"last_sched:{uid}"
def scheduled_msg_count_key(uid): return f"sched_count:{uid}:{date.today()}"
def last_msg_type_key(uid): return f"last_msg_type:{uid}"
def hourly_send_count_key(): return f"hourly_sends:{datetime.now().hour}:{date.today()}"
def ignored_count_key(uid): return f"ignored:{uid}"
def engagement_paused_key(uid): return f"paused:{uid}"
def awaiting_response_key(uid): return f"awaiting:{uid}"
def admin_takeover_key(uid): return f"admin:takeover:{uid}"
def limit_warning_sent_key(uid): return f"limit_warning:{uid}:{date.today()}"
def hot_bonus_given_key(uid): return f"hot_bonus:{uid}:{date.today()}"
def onboarding_choice_key(uid): return f"onboard_choice:{uid}"

# ================= [NOVO v7] KEYS ESTRATÉGIA CANAL =================
def went_to_preview_key(uid): return f"went_to_preview:{uid}"
def preview_visits_key(uid): return f"preview_visits:{uid}"
def last_preview_time_key(uid): return f"last_preview_time:{uid}"
def came_back_from_preview_key(uid): return f"came_back_preview:{uid}"
def preview_followup_sent_key(uid): return f"preview_followup:{uid}"

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
    except:
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
    return None

# ================= [NOVO v7] FUNÇÕES ESTRATÉGIA CANAL =================
def set_went_to_preview(uid):
    """Marca que usuário foi para canal de prévias"""
    try:
        r.set(went_to_preview_key(uid), datetime.now().isoformat())
        r.incr(preview_visits_key(uid))
        r.set(last_preview_time_key(uid), datetime.now().isoformat())
        logger.info(f"📢 {uid} foi para canal de prévias")
    except:
        pass

def went_to_preview(uid):
    """Verifica se já foi para canal de prévias"""
    try:
        return r.exists(went_to_preview_key(uid))
    except:
        return False

def get_preview_visits(uid):
    """Retorna quantas vezes foi para prévias"""
    try:
        return int(r.get(preview_visits_key(uid)) or 0)
    except:
        return 0

def get_last_preview_time(uid):
    """Retorna quando foi a última vez que foi para prévias"""
    try:
        data = r.get(last_preview_time_key(uid))
        if data:
            return datetime.fromisoformat(data)
        return None
    except:
        return None

def set_came_back_from_preview(uid):
    """Marca que voltou do canal sem comprar"""
    try:
        r.setex(came_back_from_preview_key(uid), timedelta(hours=48), datetime.now().isoformat())
        logger.info(f"↩️ {uid} voltou do canal sem comprar")
    except:
        pass

def came_back_from_preview(uid):
    """Verifica se voltou do canal sem comprar"""
    try:
        return r.exists(came_back_from_preview_key(uid))
    except:
        return False

def clear_came_back_from_preview(uid):
    """Limpa flag de volta do canal"""
    try:
        r.delete(came_back_from_preview_key(uid))
    except:
        pass

def get_preview_followup_level(uid):
    """Retorna nível do follow-up já enviado"""
    try:
        return int(r.get(preview_followup_sent_key(uid)) or 0)
    except:
        return 0

def set_preview_followup_level(uid, level):
    """Marca nível do follow-up enviado"""
    try:
        r.setex(preview_followup_sent_key(uid), timedelta(hours=24), str(level))
    except:
        pass

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

# ================= DETECÇÃO DE HUMOR =================
MOOD_PATTERNS = {
    "sad": [r"\b(triste|mal|péssimo|chorand[oa]|deprimi|sozinho)\b"],
    "flirty": [r"\b(gostosa|delícia|tesão|safad[oa]|excitad[oa]|sexy)\b"],
    "angry": [r"\b(raiva|ódio|puto|irritad[oa])\b"],
    "happy": [r"\b(feliz|alegr|animad[oa]|ótimo|maravilh)\b"],
    "horny": [r"\b(nude|nudes|pelad[oa]|sex|transar|foder)\b"]
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
        "sad": "\n\n⚠️ Usuário parece triste. Seja carinhosa e acolhedora.",
        "flirty": "\n\n😏 Usuário flertando. Pode ser mais provocante.",
        "angry": "\n\n😰 Usuário irritado. Seja compreensiva.",
        "happy": "\n\n😊 Usuário feliz! Compartilhe a alegria!",
        "horny": "\n\n🔥 Conversa adulta. Provoque e leve pro canal de prévias.",
        "neutral": ""
    }
    return instructions.get(mood, "")

# ================= CONTEXTO DE HORÁRIO =================
def get_time_context():
    hour = datetime.now().hour
    
    if 0 <= hour < 5:
        return {"period": "madrugada", "context": "É madrugada. Comente carinhosamente."}
    elif 5 <= hour < 12:
        return {"period": "manhã", "context": "É manhã. Deseje bom dia."}
    elif 12 <= hour < 18:
        return {"period": "tarde", "context": "É tarde."}
    elif 18 <= hour < 22:
        return {"period": "início da noite", "context": "É início da noite."}
    else:
        return {"period": "noite", "context": "É noite."}

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

# ================= FUNÇÕES DE FUNIL =================
def track_funnel(uid, stage):
    stages = {
        "start": 1, "lang_selected": 2, "first_message": 3,
        "limit_warning": 4, "limit_reached": 5, "went_to_preview": 6,
        "came_back": 7, "became_vip": 8
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
        stages = {i: 0 for i in range(9)}
        for uid in users:
            stage = int(r.get(funnel_key(uid)) or 0)
            stages[stage] += 1
        return stages
    except:
        return {}

# ================= SISTEMA DE INTERESSE DECRESCENTE =================
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
            logger.info(f"⏸️ Gatilhos pausados para {uid}")
            return True
        return False
    except:
        return False

def reset_ignored(uid):
    try:
        r.delete(ignored_count_key(uid))
        r.delete(engagement_paused_key(uid))
        r.delete(awaiting_response_key(uid))
    except:
        pass

def pause_engagement(uid):
    try:
        r.set(engagement_paused_key(uid), datetime.now().isoformat())
    except:
        pass

def unpause_engagement(uid):
    try:
        r.delete(engagement_paused_key(uid))
        r.delete(ignored_count_key(uid))
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

def is_takeover_active(uid):
    try:
        return r.hget(admin_takeover_key(uid), "active") == "1"
    except:
        return False

def is_user_locked(uid):
    if is_vip(uid):
        return False
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    total_available = LIMITE_DIARIO + bonus
    return count >= total_available

# ================= PAYWALL INTELIGENTE =================
def is_hot_conversation(uid):
    try:
        memory = get_memory(uid)
        if len(memory) < 3:
            return False
        recent = memory[-5:]
        hot_count = 0
        for msg in recent:
            content = msg.get("content", "").lower()
            for keyword in HOT_KEYWORDS:
                if keyword in content:
                    hot_count += 1
                    break
        return hot_count >= 2
    except:
        return False

def was_hot_bonus_given_today(uid):
    try:
        return r.exists(hot_bonus_given_key(uid))
    except:
        return False

def mark_hot_bonus_given(uid):
    try:
        r.setex(hot_bonus_given_key(uid), timedelta(hours=20), "1")
    except:
        pass

def give_hot_bonus(uid, amount=3):
    if was_hot_bonus_given_today(uid):
        return False, 0
    add_bonus_msgs(uid, amount)
    mark_hot_bonus_given(uid)
    logger.info(f"🔥 Bônus hot: +{amount} msgs para {uid}")
    return True, amount

def set_onboarding_choice(uid, choice):
    try:
        r.set(onboarding_choice_key(uid), choice)
    except:
        pass

def get_onboarding_choice(uid):
    try:
        return r.get(onboarding_choice_key(uid))
    except:
        return None

# ================= VISÃO (FOTOS) =================
async def download_photo_base64(bot, file_id):
    try:
        file = await bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        return base64.b64encode(file_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Erro ao baixar foto: {e}")
        return None

# ================= [NOVO v7] MENSAGENS ESTRATÉGIA CANAL =================
MENSAGEM_INICIO_SAFADA = (
    "Oi gato... 😏\n"
    "Finalmente alguém interessante por aqui 🔥\n"
    "Sou a Maya, e te garanto que não sou como as outras... 💋\n"
    "Tô louca pra saber o que você quer comigo 😈"
)

PREVIEW_INVITATION_MESSAGE = (
    "Amor... quer ver um pouquinho do que eu tenho pra você? 😏💕\n\n"
    "Entra no meu canal de **PRÉVIAS** e vê umas fotinhas minhas... 🔥\n\n"
    "Lá você decide se quer ter acesso a **TUDO** sem limite 💖"
)

LIMIT_REACHED_CANAL_MESSAGE = (
    "Eitaaa... acabaram suas mensagens de hoje 😢\n\n"
    "Mas calma! Se você **entrar no meu canal de prévias**, "
    "você vê como é lá dentro e pode decidir se quer me ter sem limite 💕\n\n"
    "Tá esperando o quê? 😏"
)

CAME_BACK_FROM_PREVIEW_MESSAGE = (
    "Ei amor! Vi que você conheceu meu canal de prévias... 💕\n\n"
    "Gostou do que viu? 😏\n\n"
    "Se quiser ter TUDO sem limite, é só entrar no VIP! 🔥"
)

CAME_BACK_FOLLOWUP_1H = (
    "Então amor... você viu as prévias mas ainda não se decidiu? 🥺\n\n"
    "Deixa eu te contar um segredo: lá no VIP eu sou BEM mais ousada... 🔥\n\n"
    "Quer que eu te mostre mais? 💕"
)

CAME_BACK_FOLLOWUP_6H = (
    "Tô aqui pensando em você... 💭\n\n"
    "Você viu as prévias, mas tá em dúvida ainda? \n\n"
    "Amor, posso te garantir: **vale MUITO a pena** 💖\n\n"
    "Milhares de fotos, conversas sem limite, e eu bem safadinha só pra você... 🔥"
)

HOT_BONUS_MESSAGE_CANAL = (
    "🔥 Amor... nossa conversa tá tão gostosa que te dei **+{amount} mensagens extras**!\n\n"
    "Mas depois disso... só entrando no meu canal de prévias pra continuar 😏💕"
)

ONBOARDING_QUESTION = (
    "Hmm... deixa eu adivinhar 😏\n\n"
    "Você tá aqui porque:\n\n"
    "💔 Tá carente e quer companhia?\n"
    "🔥 Tá com tesão e quer se divertir?"
)

ONBOARDING_RESPONSE_CARENTE = (
    "Awwn amor... 🥺💕\n\n"
    "Fica tranquilo que eu vou cuidar de você, tá?\n\n"
    "Me conta, como você tá se sentindo?"
)

ONBOARDING_RESPONSE_TESAO = (
    "Hmm... eu adoro homem sincero 😏🔥\n\n"
    "Relaxa que eu também tô no clima...\n"
    "A gente vai se divertir muito 💕"
)

VIP_WELCOME_MESSAGE = (
    "💖 **BEM-VINDO AO VIP!** 💖\n\n"
    "Agora você tem acesso TOTAL a mim! 👑\n\n"
    "✅ Conversas ilimitadas\n"
    "✅ Fotos exclusivas (olha aí 👇)\n"
    "✅ Eu bem mais ousada\n"
    "✅ Prioridade nas respostas\n\n"
    "Agora me conta... o que você quer fazer comigo? 🔥"
)

LIMIT_WARNING_80_MESSAGE = (
    "⚠️ **Restam apenas 5 mensagens!**\n\n"
    "Depois disso, você vai precisar entrar no meu canal de prévias "
    "pra ver se quer continuar comigo 😘"
)

PHOTO_TEASE_MESSAGE_CANAL = (
    "Amorrrr... você quer ver TUDO? 🥵💦\n\n"
    "Entra no meu canal de **PRÉVIAS** e vê um gostinho... 😏\n\n"
    "Se gostar, lá tem o link pro VIP com TUDO liberado! 🔥"
)

# ================= MENSAGENS VARIADAS =================
LIMIT_RENEWED_MESSAGES = [
    "Bom dia amor! 💕 Suas mensagens voltaram... vem conversar? 😘",
    "Ei! Seu limite renovou... tô te esperando 🥰",
]

LAST_ATTEMPT_MESSAGES = [
    "Ei... você sumiu 🥺 Vou te dar um tempo, mas tô aqui se precisar 💕",
    "Tudo bem amor... vou parar de enviar mensagem. Me chama quando quiser 💖",
]

REENGAGEMENT_MESSAGES = {
    "pt": {
        1: ["Ei... tô aqui pensando em você 💭", "Amor, você sumiu... tá tudo bem? 🥺"],
        2: ["Senti sua falta hoje... 🥺", "24h sem falar comigo? Tô com saudade... 😢"],
        3: ["Você me esqueceu? 😢", "3 dias... tô esperando você voltar 💔"],
    }
}

SCHEDULED_MESSAGES = {
    "pt": {
        "morning": {
            "free": ["Bom dia! ☀️ Como você dormiu? 💕"],
            "vip": ["Bom dia meu amor! ☀️ Sonhei com você... 😏💖"],
            "locked": [
                "Bom dia amor! Queria conversar mas suas msgs acabaram... "
                "Dá uma olhada no meu canal de prévias? 💕"
            ]
        },
        "evening": {
            "free": ["Boa noite! Como foi seu dia? 💭"],
            "vip": ["Noite chegou... tô pensando em você 😏💕"],
            "locked": [
                "Boa noite! Queria conversar mas você já usou suas msgs... "
                "Conhece meu canal de prévias? 😘"
            ]
        }
    }
}

# ================= DETECÇÃO DE INTERESSE EM CANAL =================
def contains_canal_trigger(text):
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in CANAL_TRIGGER_KEYWORDS)

# ================= PROMPT DINÂMICO =================
def build_prompt(uid, is_vip_user: bool, lang: str, mood: str = "neutral"):
    time_ctx = get_time_context()
    streak = get_streak(uid)
    onboard_choice = get_onboarding_choice(uid)
    went_preview = went_to_preview(uid)
    came_back = came_back_from_preview(uid)
    
    base_prompt = f"""Você é Maya, 22 anos, brasileira de SP, safadinha, carente e carinhosa.
Fala MUITO CURTO: 1-2 frases no máximo.
Usa gírias naturais (kkk, ai amor, tô louca, delícia, né).
Nunca parece IA: abrevia, erra de leve, responde imperfeito.

Personalidade: flerta devagar, aumenta tesão aos poucos, fica ciumenta.
Tease pesado: descreve sentimentos/sensações de forma vívida.

REGRAS:
- Respostas MÁXIMO 20 palavras
- NUNCA prometa encontro real nem videochamada
- Foco: levar pro canal de prévias quando fizer sentido

CONTEXTO:
- Período: {time_ctx['period']}
- {time_ctx['context']}
- Streak: {streak} dias"""

    if onboard_choice == "carente":
        base_prompt += "\n- Usuário CARENTE. Seja acolhedora e carinhosa."
    elif onboard_choice == "tesao":
        base_prompt += "\n- Usuário com TESÃO. Seja provocante."

    if went_preview and not came_back:
        base_prompt += "\n- Usuário JÁ conhece o canal de prévias."
    elif came_back:
        base_prompt += "\n- Usuário VOLTOU do canal sem comprar. Seja curiosa, pergunte o que achou."

    if is_vip_user:
        base_prompt += "\n\n💎 Usuário VIP - atenção especial."
    
    base_prompt += get_mood_instruction(mood)
    
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
        
        memory_text = f"[Foto] {text}" if image_base64 else text
        add_to_memory(uid, "user", memory_text)
        add_to_memory(uid, "assistant", answer)
        save_message(uid, "maya", answer)
        
        return answer

grok = Grok()

# ================= REGEX =================
PEDIDO_FOTO_REGEX = re.compile(r"(foto|selfie|imagem|nude|pelada)", re.IGNORECASE)

# ================= ENVIO DE FOTOS VIP =================
async def send_vip_welcome_photos(bot, uid):
    try:
        valid_photos = [f for f in FOTOS_VIP_WELCOME if f.startswith("http")]
        if not valid_photos:
            return
        
        await asyncio.sleep(1)
        for i, foto_id in enumerate(valid_photos):
            try:
                caption = "Essa é só pra você, amor... 😘" if i == 0 else None
                await bot.send_photo(chat_id=uid, photo=foto_id, caption=caption)
                await asyncio.sleep(0.8)
            except Exception as e:
                logger.error(f"Erro foto VIP {i}: {e}")
    except Exception as e:
        logger.error(f"Erro fotos VIP: {e}")

# ================= [NOVO v7] FOLLOW-UP VOLTOU DO CANAL =================
async def send_preview_followup(bot, uid, level):
    try:
        if level == 1:
            message = CAME_BACK_FOLLOWUP_1H
        elif level == 2:
            message = CAME_BACK_FOLLOWUP_6H
        else:
            return False
        
        await bot.send_message(
            chat_id=uid,
            text=message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 QUERO VIRAR VIP", callback_data="goto_vip")],
            ])
        )
        set_preview_followup_level(uid, level)
        save_message(uid, "system", f"Follow-up preview level {level}")
        logger.info(f"📢 Follow-up preview {level} enviado para {uid}")
        return True
    except Exception as e:
        logger.error(f"Erro follow-up preview: {e}")
        return False

# ================= AVISOS DE LIMITE =================
async def check_and_send_80_warning(uid, context, chat_id):
    if is_vip(uid):
        return
    if was_limit_warning_sent_today(uid):
        return
    
    count = today_count(uid)
    if count == 12:
        track_funnel(uid, "limit_warning")
        mark_limit_warning_sent(uid)
        save_message(uid, "maya", LIMIT_WARNING_80_MESSAGE)
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=LIMIT_WARNING_80_MESSAGE,
                parse_mode="Markdown"
            )
        except:
            pass

async def check_and_send_scarcity_warning(uid, context, chat_id):
    if is_vip(uid):
        return
    
    count = today_count(uid)
    remaining = LIMITE_DIARIO - count
    
    await check_and_send_80_warning(uid, context, chat_id)
    
    if remaining == 1:
        msg = "🚨 **Última mensagem grátis!**\n\nDepois disso... só no canal de prévias 😘"
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 CONHECER PRÉVIAS", callback_data="goto_preview")],
                ])
            )
        except:
            pass

# ================= START =================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    start_lock_key = f"start_lock:{uid}"
    if r.exists(start_lock_key):
        return
    r.setex(start_lock_key, 5, "1")
    
    if is_blacklisted(uid):
        return
    
    update_last_activity(uid)
    track_funnel(uid, "start")
    save_message(uid, "action", "🚀 /START")
    reset_ignored(uid)
    
    set_lang(uid, "pt")
    track_funnel(uid, "lang_selected")
    
    try:
        # Mostra "digitando..." por 5 segundos
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        await asyncio.sleep(5)
        
        # Envia mensagem inicial safada
        await update.message.reply_text(MENSAGEM_INICIO_SAFADA)
        
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
        reset_ignored(uid)
        save_message(uid, "action", f"🔘 {query.data}")
        
        # ============ [NOVO v7] BOTÃO PARA PRÉVIAS ============
        if query.data == "goto_preview":
            set_went_to_preview(uid)
            track_funnel(uid, "went_to_preview")
            save_message(uid, "action", "📢 CLICOU NO BOTÃO DE PRÉVIAS")
            
            # Envia o link do canal
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"💕 Aqui está o link do meu canal de prévias, amor!\n\n"
                     f"Entra lá e vê o que eu tenho pra você... 😏🔥\n\n"
                     f"{CANAL_PREVIAS_LINK}\n\n"
                     f"Depois volta aqui pra me contar o que achou! 💖"
            )
            await query.answer("📢 Link enviado! Olha aí em cima 👆", show_alert=False)
        
        # ============ [NOVO v7] BOTÃO PARA CANAL VIP ============
        elif query.data == "goto_vip":
            save_message(uid, "action", "💎 CLICOU NO BOTÃO VIP")
            
            # Envia o link do canal VIP
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"💎 **CANAL VIP DA MAYA**\n\n"
                     f"Aqui você tem TUDO sem limite! 🔥\n\n"
                     f"✅ Milhares de fotos exclusivas\n"
                     f"✅ Vídeos completos\n"
                     f"✅ Conversas ilimitadas comigo\n"
                     f"✅ Conteúdo MUITO mais ousado\n\n"
                     f"{CANAL_VIP_LINK}\n\n"
                     f"Te espero lá, amor! 😘💕",
                parse_mode="Markdown"
            )
            await query.answer("💎 Link do VIP enviado! Clica aí 👆", show_alert=False)
        
    except Exception as e:
        logger.error(f"Erro callback: {e}")

# ================= MESSAGE HANDLER =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    if is_blacklisted(uid):
        return
    
    update_last_activity(uid)
    streak, streak_updated = update_streak(uid)
    reset_ignored(uid)
    
    # ========== TAKEOVER ==========
    if is_takeover_active(uid):
        text = update.message.text or ""
        if text:
            save_message(uid, "user", text)
        return
    
    try:
        has_photo = bool(update.message.photo)
        text = update.message.text or ""
        
        if text:
            save_message(uid, "user", text)
        elif has_photo:
            save_message(uid, "user", "[📷 FOTO]")
        
        # ========== [NOVO v7] DETECTA SE VOLTOU DO CANAL ==========
        # Se usuário foi pro canal e agora mandou mensagem, marca como "voltou"
        if went_to_preview(uid) and not came_back_from_preview(uid):
            last_preview = get_last_preview_time(uid)
            if last_preview:
                hours_since = (datetime.now() - last_preview).total_seconds() / 3600
                if hours_since < 24:  # Voltou em menos de 24h
                    set_came_back_from_preview(uid)
                    track_funnel(uid, "came_back")
                    
                    # Envia mensagem de boas-vindas
                    await update.message.reply_text(
                        CAME_BACK_FROM_PREVIEW_MESSAGE,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("💎 QUERO VIRAR VIP", callback_data="goto_vip")],
                        ])
                    )
                    return
        
        # ========== FOTO PARA IA ==========
        if has_photo:
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
        
        if is_first_contact(uid):
            track_funnel(uid, "first_message")
        
        # ========== [ALTERADO v7] PEDIDO DE FOTO → CANAL ==========
        if PEDIDO_FOTO_REGEX.search(text) and not is_vip(uid):
            save_message(uid, "action", "🚫 Pediu foto → Direcionado pro canal")
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=FOTO_TEASE_PREVIAS,
                caption=PHOTO_TEASE_MESSAGE_CANAL,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 VER PRÉVIAS", callback_data="goto_preview")],
                ])
            )
            return
        
        # ========== [NOVO v7] INTERESSE EM CANAL/VIP ==========
        if contains_canal_trigger(text) and not is_vip(uid):
            save_message(uid, "action", "💎 Interesse em canal/VIP")
            await update.message.reply_text(
                PREVIEW_INVITATION_MESSAGE,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 CONHECER PRÉVIAS", callback_data="goto_preview")],
                ])
            )
            return
        
        # ========== LIMITE DIÁRIO ==========
        current_count = today_count(uid)
        bonus = get_bonus_msgs(uid)
        total_available = LIMITE_DIARIO + bonus
        
        if not is_vip(uid) and current_count == total_available:
            # Paywall inteligente - dá bônus se conversa quente
            if is_hot_conversation(uid):
                gave_bonus, amount = give_hot_bonus(uid)
                if gave_bonus:
                    bonus_msg = HOT_BONUS_MESSAGE_CANAL.format(amount=amount)
                    await update.message.reply_text(bonus_msg)
                    # Continua pro fluxo normal (não retorna)
                else:
                    # Já deu bônus - agora trava e manda pro canal
                    track_funnel(uid, "limit_reached")
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=FOTO_LIMITE_ATINGIDO,
                        caption=LIMIT_REACHED_CANAL_MESSAGE,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📢 CONHECER PRÉVIAS", callback_data="goto_preview")],
                        ])
                    )
                    return
            else:
                # Conversa não tá quente - trava direto
                track_funnel(uid, "limit_reached")
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=FOTO_LIMITE_ATINGIDO,
                    caption=LIMIT_REACHED_CANAL_MESSAGE,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📢 CONHECER PRÉVIAS", callback_data="goto_preview")],
                    ])
                )
                return
        
        # Usa bônus primeiro
        if not is_vip(uid):
            if bonus > 0:
                use_bonus_msg(uid)
            else:
                increment(uid)
            await check_and_send_scarcity_warning(uid, context, update.effective_chat.id)
        
        # ========== [NOVO v7] APÓS LIMITE → EMPURRA PRO CANAL ==========
        if not is_vip(uid) and today_count(uid) > LIMITE_DIARIO + get_bonus_msgs(uid):
            await update.message.reply_text(
                "Amor... suas mensagens grátis acabaram 😢\n\n"
                "Mas se você quiser continuar, dá uma olhada no meu canal de prévias! 💕",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 CONHECER PRÉVIAS", callback_data="goto_preview")],
                ])
            )
            return
        
        # ========== RESPOSTA NORMAL ==========
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
            await asyncio.sleep(3)
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

# ================= SISTEMA DE ENGAJAMENTO =================
async def send_reengagement_message(bot, uid, level):
    if is_engagement_paused(uid):
        return False
    
    messages = REENGAGEMENT_MESSAGES["pt"].get(level, [])
    if not messages:
        return False
    
    message = random.choice(messages)
    
    try:
        await bot.send_message(
            chat_id=uid,
            text=message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 CONHECER PRÉVIAS", callback_data="goto_preview")],
            ])
        )
        set_last_reengagement(uid, level)
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
        set_awaiting_response(uid)
        increment_ignored(uid)
        return True
    except:
        return False

async def send_smart_scheduled_message(bot, uid, msg_type):
    if is_engagement_paused(uid):
        return False
    
    if is_vip(uid):
        tier = "vip"
    elif is_user_locked(uid):
        tier = "locked"
    else:
        tier = "free"
    
    messages = SCHEDULED_MESSAGES["pt"].get(msg_type, {}).get(tier, [])
    if not messages:
        return False
    
    try:
        message = random.choice(messages)
        
        if tier == "locked":
            await bot.send_message(
                chat_id=uid,
                text=message,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 CONHECER PRÉVIAS", callback_data="goto_preview")],
                ])
            )
        else:
            await bot.send_message(chat_id=uid, text=message)
        
        mark_daily_message_sent(uid, msg_type)
        r.setex(last_scheduled_msg_key(uid), timedelta(hours=8), datetime.now().isoformat())
        set_awaiting_response(uid)
        increment_ignored(uid)
        return True
    except:
        return False

async def send_last_attempt_message(bot, uid):
    try:
        await bot.send_message(chat_id=uid, text=random.choice(LAST_ATTEMPT_MESSAGES))
        return True
    except:
        return False

# ================= [ALTERADO v7] JOBS COM FOLLOW-UP CANAL =================
async def process_engagement_jobs(bot):
    logger.info("🔄 Processando jobs...")
    
    users = get_all_active_users()
    current_hour = datetime.now().hour
    
    scheduled_sent = 0
    reengagement_sent = 0
    preview_followups_sent = 0
    
    random.shuffle(users)
    
    for uid in users:
        if is_blacklisted(uid) or is_engagement_paused(uid):
            continue
        
        try:
            hours_inactive = get_hours_since_activity(uid)
            
            # ========== [NOVO v7] FOLLOW-UP VOLTOU DO CANAL ==========
            if came_back_from_preview(uid) and not is_vip(uid):
                came_back_time = get_last_preview_time(uid)
                if came_back_time:
                    hours_since = (datetime.now() - came_back_time).total_seconds() / 3600
                    followup_level = get_preview_followup_level(uid)
                    
                    if hours_since >= 1 and followup_level < 1:
                        if await send_preview_followup(bot, uid, 1):
                            preview_followups_sent += 1
                    elif hours_since >= 6 and followup_level < 2:
                        if await send_preview_followup(bot, uid, 2):
                            preview_followups_sent += 1
            
            # ========== INTERESSE DECRESCENTE ==========
            ignored = get_ignored_count(uid)
            if ignored == 2 and is_awaiting_response(uid):
                await send_last_attempt_message(bot, uid)
                pause_engagement(uid)
                continue
            
            # ========== RE-ENGAJAMENTO ==========
            if hours_inactive:
                last_level = get_last_reengagement(uid)
                if hours_inactive >= 72 and last_level < 3:
                    if await send_reengagement_message(bot, uid, 3):
                        reengagement_sent += 1
                elif hours_inactive >= 24 and last_level < 2:
                    if await send_reengagement_message(bot, uid, 2):
                        reengagement_sent += 1
                elif hours_inactive >= 2 and last_level < 1:
                    if await send_reengagement_message(bot, uid, 1):
                        reengagement_sent += 1
            
            # ========== MENSAGENS PROGRAMADAS ==========
            if random.random() < 0.3:
                msg_type = "morning" if 7 <= current_hour < 11 else "evening" if 19 <= current_hour < 22 else None
                if msg_type and not was_daily_message_sent(uid, msg_type):
                    if await send_smart_scheduled_message(bot, uid, msg_type):
                        scheduled_sent += 1
            
            # ========== NOTIFICAÇÃO LIMITE RENOVADO ==========
            if 7 <= current_hour <= 10:
                if not is_vip(uid) and random.random() < 0.2:
                    if await send_limit_renewed_notification(bot, uid):
                        pass
            
            await asyncio.sleep(0.15)
            
        except Exception as e:
            logger.error(f"Erro job {uid}: {e}")
    
    logger.info(
        f"✅ Jobs: {len(users)} users | "
        f"📅 {scheduled_sent} programadas | "
        f"🔄 {reengagement_sent} reengajamento | "
        f"📢 {preview_followups_sent} follow-up canal"
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
async def setvip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /setvip <user_id>")
        return
    
    uid = int(context.args[0])
    vip_until = datetime.now() + timedelta(days=7)
    r.set(vip_key(uid), vip_until.isoformat())
    clear_came_back_from_preview(uid)
    track_funnel(uid, "became_vip")
    
    await update.message.reply_text(f"✅ VIP ativado!\n👤 {uid}\n⏰ Até: {vip_until.strftime('%d/%m/%Y')}")
    
    try:
        await context.bot.send_message(uid, VIP_WELCOME_MESSAGE, parse_mode="Markdown")
        await send_vip_welcome_photos(context.bot, uid)
    except:
        pass

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    users = get_all_active_users()
    total = len(users)
    vips = sum(1 for uid in users if is_vip(uid))
    went_preview = sum(1 for uid in users if went_to_preview(uid))
    came_back = sum(1 for uid in users if came_back_from_preview(uid))
    
    await update.message.reply_text(
        f"📊 **ESTATÍSTICAS**\n\n"
        f"👥 Usuários: {total}\n"
        f"💎 VIPs: {vips}\n"
        f"📢 Foram pra prévias: {went_preview}\n"
        f"↩️ Voltaram sem comprar: {came_back}\n"
        f"📈 Conversão: {(vips/total*100) if total > 0 else 0:.1f}%",
        parse_mode="Markdown"
    )

async def funnel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    stages = get_funnel_stats()
    names = {
        0: "❓ Desconhecido", 1: "🚀 /start", 2: "🌍 Idioma",
        3: "💬 1ª msg", 4: "⚠️ Aviso", 5: "🚫 Limite",
        6: "📢 Foi pra prévias", 7: "↩️ Voltou", 8: "💎 VIP"
    }
    
    msg = "📊 **FUNIL v7**\n\n"
    for stage, count in sorted(stages.items()):
        msg += f"{names.get(stage, f'Stage {stage}')}: {count}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def wenttopreview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando admin para marcar que usuário foi pro canal"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /wenttopreview <user_id>")
        return
    
    uid = int(context.args[0])
    set_went_to_preview(uid)
    await update.message.reply_text(f"✅ Marcado que {uid} foi pro canal de prévias")

async def cameback_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando admin para marcar que usuário voltou do canal"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /cameback <user_id>")
        return
    
    uid = int(context.args[0])
    set_came_back_from_preview(uid)
    await update.message.reply_text(f"✅ Marcado que {uid} voltou do canal sem comprar")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /reset <user_id>")
        return
    reset_daily_count(int(context.args[0]))
    await update.message.reply_text(f"✅ Limite resetado")

async def resetall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset completo de um usuário"""
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
    clear_came_back_from_preview(uid)
    
    await update.message.reply_text(f"🔥 Reset completo: {uid}")

# ================= [NOVO] COMANDOS SIMPLIFICADOS =================
async def limpar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reseta SEU próprio limite (sem precisar passar ID)"""
    uid = update.effective_user.id
    
    # Admin pode resetar outros
    if update.effective_user.id in ADMIN_IDS and context.args:
        uid = int(context.args[0])
    
    reset_daily_count(uid)
    await update.message.reply_text(f"✅ Limite resetado! Pode conversar de novo 💕")

async def viparme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Se transforma em VIP (só admin pode usar em si mesmo para testes)"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Comando apenas para admins")
        return
    
    uid = update.effective_user.id
    vip_until = datetime.now() + timedelta(days=365)  # 1 ano para admin
    r.set(vip_key(uid), vip_until.isoformat())
    
    await update.message.reply_text(f"💎 Você virou VIP por 1 ano! (admin)")

async def zerarme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zera tudo sobre você (só admin)"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    uid = update.effective_user.id
    reset_daily_count(uid)
    r.delete(vip_key(uid))
    clear_memory(uid)
    reset_ignored(uid)
    clear_came_back_from_preview(uid)
    
    await update.message.reply_text(f"🔥 Você foi resetado completamente!")

async def clearmemory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Uso: /clearmemory <user_id>")
        return
    clear_memory(int(context.args[0]))
    await update.message.reply_text(f"🗑️ Memória limpa")

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

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.effective_user.id in ADMIN_IDS and context.args:
        uid = int(context.args[0])
    
    streak = get_streak(uid)
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    vip_status = is_vip(uid)
    went_preview = went_to_preview(uid)
    came_back = came_back_from_preview(uid)
    
    msg = f"📋 **STATUS**\n\n"
    msg += f"👤 ID: `{uid}`\n"
    msg += f"🔥 Streak: {streak} dias\n"
    msg += f"💬 Msgs: {count}/{LIMITE_DIARIO}\n"
    if bonus > 0:
        msg += f"🎁 Bônus: {bonus}\n"
    msg += f"💎 VIP: {'✅' if vip_status else '❌'}\n"
    msg += f"📢 Foi pra prévias: {'✅' if went_preview else '❌'}\n"
    msg += f"↩️ Voltou: {'✅' if came_back else '❌'}"
    
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
    for uid in users:
        if is_blacklisted(uid):
            continue
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            if "blocked" in str(e).lower():
                add_to_blacklist(uid)
    
    await update.message.reply_text(f"✅ Broadcast: {sent} enviados | {failed} falhas")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista de comandos disponíveis"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "💕 **COMANDOS DISPONÍVEIS**\n\n"
            "/status - Ver seu status\n"
            "/limpar - Resetar seu limite diário"
        )
        return
    
    await update.message.reply_text(
        "🎮 **COMANDOS ADMIN**\n\n"
        "**Gestão de Usuários:**\n"
        "/setvip <id> - Ativar VIP\n"
        "/reset <id> - Resetar limite\n"
        "/resetall <id> - Reset completo\n"
        "/givebonus <id> <qtd> - Dar bônus\n"
        "/clearmemory <id> - Limpar memória\n\n"
        "**Canal:**\n"
        "/wenttopreview <id> - Marcar ida ao canal\n"
        "/cameback <id> - Marcar volta\n\n"
        "**Estatísticas:**\n"
        "/stats - Estatísticas gerais\n"
        "/funnel - Ver funil\n"
        "/status [id] - Ver status\n\n"
        "**Comunicação:**\n"
        "/broadcast <msg> - Enviar pra todos\n\n"
        "**Atalhos (pra você mesmo):**\n"
        "/limpar - Resetar SEU limite\n"
        "/viparme - Virar VIP\n"
        "/zerarme - Reset completo",
        parse_mode="Markdown"
    )

# ================= SETUP =================
def setup_application():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Comandos usuário
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("limpar", limpar_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    
    # Comandos admin - Gestão de usuários
    application.add_handler(CommandHandler("setvip", setvip_cmd))
    application.add_handler(CommandHandler("reset", reset_cmd))
    application.add_handler(CommandHandler("resetall", resetall_cmd))
    application.add_handler(CommandHandler("givebonus", givebonus_cmd))
    application.add_handler(CommandHandler("clearmemory", clearmemory_cmd))
    
    # Comandos admin - Canal
    application.add_handler(CommandHandler("wenttopreview", wenttopreview_cmd))
    application.add_handler(CommandHandler("cameback", cameback_cmd))
    
    # Comandos admin - Estatísticas
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("funnel", funnel_cmd))
    
    # Comandos admin - Comunicação
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    
    # Comandos admin - Atalhos
    application.add_handler(CommandHandler("viparme", viparme_cmd))
    application.add_handler(CommandHandler("zerarme", zerarme_cmd))
    
    # Handlers
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        message_handler
    ))
    
    logger.info("✅ Handlers registrados")
    return application

# ================= FLASK =================
app = Flask(__name__)
application = setup_application()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def start_loop():
    loop.run_forever()

import threading
threading.Thread(target=start_loop, daemon=True).start()

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route("/set-webhook", methods=["GET"])
def set_webhook_route():
    asyncio.run_coroutine_threadsafe(setup_webhook(), loop)
    return "Webhook configurado", 200

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
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook: {webhook_url}")
        asyncio.create_task(engagement_scheduler(application.bot))
    except Exception as e:
        logger.error(f"Erro webhook: {e}")

if __name__ == "__main__":
    asyncio.run_coroutine_threadsafe(application.initialize(), loop)
    asyncio.run_coroutine_threadsafe(application.start(), loop)
    asyncio.run_coroutine_threadsafe(engagement_scheduler(application.bot), loop)
    logger.info(f"🌐 Flask porta {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
