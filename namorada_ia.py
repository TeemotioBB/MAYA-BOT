#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                          🔥 SOPHIA BOT v7.2 - CLEAN                          ║
║                                                                              ║
║  ARQUITETURA: BOT → CANAL PRÉVIAS → CANAL VIP                              ║
║                                                                              ║
║  O bot é um FUNIL DE CONVERSÃO, não controla VIP.                          ║
║  VIP é gerenciado 100% no canal do Telegram.                               ║
║                                                                              ║
║  FLUXO:                                                                     ║
║  1. Lead conversa no bot (limite de 17 msgs/dia)                           ║
║  2. Ao atingir limite ou mostrar interesse → direcionado pras PRÉVIAS      ║
║  3. Nas prévias, vê conteúdo teaser + link do VIP                          ║
║  4. No VIP, conteúdo completo e ilimitado (gerenciado lá)                  ║
║                                                                              ║
║  MELHORIAS v7.2:                                                            ║
║  ✅ Removido sistema VIP do bot (não faz sentido no novo fluxo)            ║
║  ✅ Simplificado fluxo de limite (todos têm limite, sem exceção)           ║
║  ✅ Botão VIP só aparece após visitar prévias                              ║
║  ✅ Tracking real: visitou prévias, clicou VIP, voltou                     ║
║  ✅ Follow-ups inteligentes baseados no comportamento                      ║
║  ✅ Código limpo e comentado para fácil manutenção                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 📦 IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════════════════════
# ⚙️ CONFIGURAÇÃO - EDITE AQUI ANTES DO DEPLOY
# ═══════════════════════════════════════════════════════════════════════════════

# 🔑 Tokens e APIs
BOT_TOKEN = "COLE_SEU_TOKEN_BOT_AQUI"
GROK_KEY = "COLE_SUA_KEY_GROK_AQUI"

# 📢 Links dos Canais (IMPORTANTE: Use os links públicos corretos)
LINK_CANAL_PREVIAS = "https://t.me/previasdamayaofc"  # Seu canal de prévias
LINK_CANAL_VIP = "https://t.me/Mayaoficial_bot"     # Seu canal VIP (com +)

# 👤 Admin
MEU_TELEGRAM_ID = "1293602874"  # Seu ID do Telegram

# 🌐 URL do Railway (após deploy, cole aqui)
WEBHOOK_URL = "https://maya-bot-production.up.railway.app"

# ═══════════════════════════════════════════════════════════════════════════════
# ⚙️ CONFIGURAÇÕES AVANÇADAS
# ═══════════════════════════════════════════════════════════════════════════════

# Limite diário de mensagens (FREE)
LIMITE_DIARIO = 17  # 17 mensagens grátis por dia

# Sistema de tracking e follow-ups
PREVIEW_RETURN_WINDOW_HOURS = 48        # Janela pra considerar "voltou do canal"
PREVIEW_ABANDONED_HOURS = 3             # Tempo sem interagir = abandono
PREVIEW_FOLLOWUP_INTERVAL_HOURS = 12    # Intervalo entre follow-ups
HIGH_RESISTANCE_VISITS = 3              # 3+ visitas = alta resistência

# ═══════════════════════════════════════════════════════════════════════════════
# 🔧 SETUP INICIAL
# ═══════════════════════════════════════════════════════════════════════════════

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or BOT_TOKEN
GROK_API_KEY = os.getenv("GROK_API_KEY") or GROK_KEY
REDIS_URL = os.getenv("REDIS_URL", "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241")
PORT = int(os.getenv("PORT", 8080))

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

# Admin IDs
ADMIN_IDS = set(map(int, os.getenv("ADMIN_IDS", MEU_TELEGRAM_ID).split(",")))

# Links dos canais
CANAL_PREVIAS_LINK = os.getenv("CANAL_PREVIAS_LINK") or LINK_CANAL_PREVIAS
CANAL_VIP_LINK = os.getenv("CANAL_VIP_LINK") or LINK_CANAL_VIP

# Info do bot
logger.info(f"🚀 Sophia Bot v7.2 CLEAN iniciando...")
logger.info(f"📍 Webhook: {WEBHOOK_BASE_URL}{WEBHOOK_PATH}")
logger.info(f"📢 Canal Prévias: {CANAL_PREVIAS_LINK}")
logger.info(f"💎 Canal VIP: {CANAL_VIP_LINK}")
logger.info(f"📊 Limite diário: {LIMITE_DIARIO} msgs")
logger.info(f"⏰ Janela retorno: {PREVIEW_RETURN_WINDOW_HOURS}h")

# ═══════════════════════════════════════════════════════════════════════════════
# 🗄️ REDIS CONNECTION
# ═══════════════════════════════════════════════════════════════════════════════
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    logger.info("✅ Redis conectado")
except Exception as e:
    logger.error(f"❌ Redis erro: {e}")
    raise

# ═══════════════════════════════════════════════════════════════════════════════
# 🤖 CONFIGURAÇÃO GROK AI
# ═══════════════════════════════════════════════════════════════════════════════
MODELO = "grok-2-1212"
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
MAX_MEMORIA = 12  # Últimas 12 mensagens na memória

# ═══════════════════════════════════════════════════════════════════════════════
# 🎨 ASSETS (Fotos e Áudios)
# ═══════════════════════════════════════════════════════════════════════════════
AUDIO_PT_1 = "CQACAgEAAxkBAAEDDXFpaYkigGDlcTzZxaJXFuWDj1Ow5gAC5QQAAiq7UUdXWpPNiiNd1jgE"
AUDIO_PT_2 = "CQACAgEAAxkBAAEDAAEmaVRmPJ5iuBOaXyukQ06Ui23TSokAAocGAAIZwaFGkIERRmRoPes4BA"

FOTO_ONBOARDING_START = "https://i.postimg.cc/qq4NtgYQ/E775DE63-5B33-4DBB-A65F-FDD851021569.jpg"
FOTO_TEASE_PREVIAS = "https://i.postimg.cc/qq4NtgYQ/E775DE63-5B33-4DBB-A65F-FDD851021569.jpg"
FOTO_LIMITE_ATINGIDO = "https://i.postimg.cc/gjmxwr5f/IMG-8507.jpg"

# Fotos teaser para quando direcionar pro canal
FOTOS_TEASER = [
    "https://i.postimg.cc/T1fKyhFG/IMG-8691.jpg",
    "https://i.postimg.cc/4yPmpsk0/IMG-8692.jpg",
    "https://i.postimg.cc/90bryC5S/IMG-8696.jpg",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 🔑 KEYWORDS (Detecção de Intenção)
# ═══════════════════════════════════════════════════════════════════════════════

# Keywords que indicam conversa adulta/quente
HOT_KEYWORDS = [
    'pau', 'buceta', 'chupar', 'gozar', 'tesão', 'foder', 'transar',
    'punheta', 'siririca', 'safada', 'gostosa', 'pelada', 'nua',
    'chupeta', 'boquete', 'anal', 'cu', 'rola', 'pica', 'mama',
    'seios', 'peitos', 'bunda', 'xereca', 'meter', 'fuder', 'sexo',
    'excitado', 'excitada', 'molhada', 'duro', 'tesudo', 'tesuda'
]

# Keywords que indicam interesse no canal/VIP
CANAL_TRIGGER_KEYWORDS = [
    'vip', 'premium', 'ilimitado', 'ilimitada', 'sem limite',
    'quanto custa', 'preço', 'pagar', 'pagamento', 'comprar',
    'quanto é', 'quanto ta', 'quanto tá', 'valor', 'plano',
    'assinatura', 'canal', 'grupo', 'previas', 'prévia'
]

# Regex para detectar pedido de foto
PEDIDO_FOTO_REGEX = re.compile(r"(foto|selfie|imagem|nude|pelada)", re.IGNORECASE)

# ═══════════════════════════════════════════════════════════════════════════════
# 🗄️ REDIS KEYS - Organização de dados no Redis
# ═══════════════════════════════════════════════════════════════════════════════

# MEMÓRIA E PERFIL
def memory_key(uid): return f"memory:{uid}"
def user_profile_key(uid): return f"profile:{uid}"
def first_contact_key(uid): return f"first_contact:{uid}"
def lang_key(uid): return f"lang:{uid}"

# CONTROLE DIÁRIO
def count_key(uid): return f"count:{uid}:{date.today()}"
def bonus_msgs_key(uid): return f"bonus:{uid}"
def limit_notified_key(uid): return f"limit_notified:{uid}:{date.today()}"
def limit_warning_sent_key(uid): return f"limit_warning:{uid}:{date.today()}"

# ATIVIDADE E ENGAGEMENT
def last_activity_key(uid): return f"last_activity:{uid}"
def last_reengagement_key(uid): return f"last_reengagement:{uid}"
def daily_messages_sent_key(uid): return f"daily_msg_sent:{uid}:{date.today()}"
def ignored_count_key(uid): return f"ignored:{uid}"
def engagement_paused_key(uid): return f"paused:{uid}"
def awaiting_response_key(uid): return f"awaiting:{uid}"

# STREAK (dias consecutivos)
def streak_key(uid): return f"streak:{uid}"
def streak_last_day_key(uid): return f"streak_last:{uid}"

# TRACKING DE CANAL
def went_to_preview_key(uid): return f"went_to_preview:{uid}"
def preview_visits_key(uid): return f"preview_visits:{uid}"
def last_preview_time_key(uid): return f"last_preview_time:{uid}"
def came_back_from_preview_key(uid): return f"came_back_preview:{uid}"
def clicked_vip_key(uid): return f"clicked_vip:{uid}"

# FOLLOW-UPS
def preview_followup_sent_key(uid): return f"preview_followup:{uid}"
def last_preview_abandoned_followup_key(uid): return f"preview_abandoned_followup:{uid}"
def preview_abandoned_level_key(uid): return f"preview_abandoned_level:{uid}"

# FUNIL E TRACKING
def funnel_key(uid): return f"funnel:{uid}"
def onboarding_choice_key(uid): return f"onboard_choice:{uid}"

# OUTROS
def chatlog_key(uid): return f"chatlog:{uid}"
def recent_responses_key(uid): return f"recent_resp:{uid}"
def blacklist_key(): return "blacklist"
def all_users_key(): return "all_users"
def admin_takeover_key(uid): return f"admin:takeover:{uid}"

# ═══════════════════════════════════════════════════════════════════════════════
# 💾 FUNÇÕES DE MEMÓRIA (Conversação com IA)
# ═══════════════════════════════════════════════════════════════════════════════

def get_memory(uid):
    """Recupera histórico de conversa do usuário"""
    try:
        data = r.get(memory_key(uid))
        return json.loads(data) if data else []
    except:
        return []

def save_memory(uid, messages):
    """Salva histórico de conversa (últimas MAX_MEMORIA mensagens)"""
    try:
        recent = messages[-MAX_MEMORIA:] if len(messages) > MAX_MEMORIA else messages
        r.setex(memory_key(uid), timedelta(days=7), json.dumps(recent, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Erro salvar memória: {e}")

def add_to_memory(uid, role, content):
    """Adiciona mensagem à memória"""
    memory = get_memory(uid)
    memory.append({"role": role, "content": content})
    save_memory(uid, memory)

def clear_memory(uid):
    """Limpa memória do usuário"""
    try:
        r.delete(memory_key(uid))
        logger.info(f"🗑️ Memória limpa: {uid}")
    except Exception as e:
        logger.error(f"Erro limpar memória: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# 👤 FUNÇÕES DE PERFIL DO USUÁRIO
# ═══════════════════════════════════════════════════════════════════════════════

def get_user_profile(uid):
    """Recupera perfil do usuário"""
    try:
        data = r.get(user_profile_key(uid))
        return json.loads(data) if data else {}
    except:
        return {}

def save_user_profile(uid, profile):
    """Salva perfil do usuário"""
    try:
        r.set(user_profile_key(uid), json.dumps(profile, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Erro salvar perfil: {e}")

def get_user_name(uid):
    """Retorna nome do usuário"""
    return get_user_profile(uid).get("name", "")

# ═══════════════════════════════════════════════════════════════════════════════
# 🚫 BLACKLIST (Usuários bloqueados)
# ═══════════════════════════════════════════════════════════════════════════════

def is_blacklisted(uid):
    try:
        return r.sismember(blacklist_key(), str(uid))
    except:
        return False

def add_to_blacklist(uid):
    try:
        r.sadd(blacklist_key(), str(uid))
        logger.info(f"🚫 Adicionado à blacklist: {uid}")
    except:
        pass

def remove_from_blacklist(uid):
    try:
        r.srem(blacklist_key(), str(uid))
        logger.info(f"✅ Removido da blacklist: {uid}")
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# 🎁 SISTEMA DE BÔNUS (Mensagens extras)
# ═══════════════════════════════════════════════════════════════════════════════
# NOTA: Sistema opcional. Pode ser removido se preferir não dar bônus.

def get_bonus_msgs(uid):
    """Retorna quantas mensagens bônus o usuário tem"""
    try:
        return int(r.get(bonus_msgs_key(uid)) or 0)
    except:
        return 0

def add_bonus_msgs(uid, amount):
    """Adiciona mensagens bônus"""
    try:
        current = get_bonus_msgs(uid)
        r.setex(bonus_msgs_key(uid), timedelta(days=7), current + amount)
        logger.info(f"🎁 +{amount} bônus para {uid} (total: {current + amount})")
    except:
        pass

def use_bonus_msg(uid):
    """Usa uma mensagem bônus (retorna True se tinha bônus)"""
    try:
        current = get_bonus_msgs(uid)
        if current > 0:
            r.set(bonus_msgs_key(uid), current - 1)
            r.expire(bonus_msgs_key(uid), timedelta(days=7))
            return True
        return False
    except:
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# 🔥 STREAK SYSTEM (Dias consecutivos de conversa)
# ═══════════════════════════════════════════════════════════════════════════════

def get_streak(uid):
    """Retorna streak atual"""
    try:
        return int(r.get(streak_key(uid)) or 0)
    except:
        return 0

def update_streak(uid):
    """Atualiza streak do usuário. Retorna (streak_atual, foi_atualizado)"""
    try:
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        last_day = r.get(streak_last_day_key(uid))
        
        if last_day == today:
            # Já interagiu hoje
            return get_streak(uid), False
        elif last_day == yesterday:
            # Interagiu ontem, incrementa streak
            new_streak = get_streak(uid) + 1
            r.set(streak_key(uid), new_streak)
            r.set(streak_last_day_key(uid), today)
            return new_streak, True
        else:
            # Quebrou o streak, recomeça
            r.set(streak_key(uid), 1)
            r.set(streak_last_day_key(uid), today)
            return 1, True
    except:
        return 0, False

def get_streak_message(streak):
    """Retorna mensagem de milestone se aplicável"""
    if streak < 3:
        return None
    elif streak == 3:
        return "🔥 3 dias seguidos conversando comigo! Tô amando isso 💕"
    elif streak == 5:
        return "🔥🔥 5 dias seguidos! Você é especial demais 💖"
    elif streak == 7:
        return "🔥🔥🔥 UMA SEMANA INTEIRA! Você é oficialmente meu favorito 😍💕"
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# 📢 TRACKING DE CANAL (Core do sistema de funil)
# ═══════════════════════════════════════════════════════════════════════════════

def set_went_to_preview(uid):
    """Marca que usuário clicou no link de prévias"""
    try:
        now = datetime.now()
        r.set(went_to_preview_key(uid), now.isoformat())
        r.incr(preview_visits_key(uid))
        r.set(last_preview_time_key(uid), now.isoformat())
        visits = get_preview_visits(uid)
        logger.info(f"📢 {uid} foi para canal de prévias (visita #{visits})")
    except Exception as e:
        logger.error(f"Erro set_went_to_preview: {e}")

def went_to_preview(uid):
    """Verifica se usuário já visitou prévias alguma vez"""
    try:
        return r.exists(went_to_preview_key(uid))
    except:
        return False

def get_preview_visits(uid):
    """Retorna quantas vezes visitou o canal de prévias"""
    try:
        return int(r.get(preview_visits_key(uid)) or 0)
    except:
        return 0

def get_last_preview_time(uid):
    """Retorna quando foi a última visita ao canal"""
    try:
        data = r.get(last_preview_time_key(uid))
        return datetime.fromisoformat(data) if data else None
    except:
        return None

def set_came_back_from_preview(uid):
    """Marca que usuário voltou do canal sem converter"""
    try:
        r.setex(
            came_back_from_preview_key(uid),
            timedelta(hours=PREVIEW_RETURN_WINDOW_HOURS),
            datetime.now().isoformat()
        )
        logger.info(f"↩️ {uid} voltou do canal sem converter")
    except Exception as e:
        logger.error(f"Erro set_came_back: {e}")

def came_back_from_preview(uid):
    """Verifica se usuário voltou do canal recentemente"""
    try:
        return r.exists(came_back_from_preview_key(uid))
    except:
        return False

def set_clicked_vip(uid):
    """Marca que usuário clicou no link do VIP"""
    try:
        r.set(clicked_vip_key(uid), datetime.now().isoformat())
        logger.info(f"💎 {uid} clicou no link VIP")
    except:
        pass

def clicked_vip(uid):
    """Verifica se usuário já clicou no VIP"""
    try:
        return r.exists(clicked_vip_key(uid))
    except:
        return False

def is_high_resistance_user(uid):
    """Verifica se é usuário de alta resistência (visitou muito mas não converteu)"""
    return get_preview_visits(uid) >= HIGH_RESISTANCE_VISITS

# ═══════════════════════════════════════════════════════════════════════════════
# 📊 FOLLOW-UP TRACKING
# ═══════════════════════════════════════════════════════════════════════════════

def get_preview_followup_level(uid):
    """Nível do follow-up enviado para quem voltou"""
    try:
        return int(r.get(preview_followup_sent_key(uid)) or 0)
    except:
        return 0

def set_preview_followup_level(uid, level):
    """Marca nível do follow-up enviado"""
    try:
        r.setex(preview_followup_sent_key(uid), timedelta(hours=24), str(level))
    except Exception as e:
        logger.error(f"Erro set_followup_level: {e}")

def get_last_abandoned_followup_time(uid):
    """Quando foi enviado último follow-up de abandono"""
    try:
        data = r.get(last_preview_abandoned_followup_key(uid))
        return datetime.fromisoformat(data) if data else None
    except:
        return None

def set_last_abandoned_followup_time(uid):
    """Marca quando foi enviado follow-up de abandono"""
    try:
        r.set(last_preview_abandoned_followup_key(uid), datetime.now().isoformat())
    except:
        pass

def get_abandoned_followup_level(uid):
    """Quantos follow-ups de abandono foram enviados"""
    try:
        return int(r.get(preview_abandoned_level_key(uid)) or 0)
    except:
        return 0

def increment_abandoned_followup_level(uid):
    """Incrementa contador de follow-ups de abandono"""
    try:
        level = get_abandoned_followup_level(uid) + 1
        r.setex(preview_abandoned_level_key(uid), timedelta(days=7), str(level))
        return level
    except:
        return 1

# ═══════════════════════════════════════════════════════════════════════════════
# 🔄 ANTI-REPETIÇÃO (Evita IA repetir mesma resposta)
# ═══════════════════════════════════════════════════════════════════════════════

def get_response_hash(text):
    """Gera hash da resposta"""
    return hashlib.md5(text.encode()).hexdigest()[:8]

def is_response_recent(uid, response):
    """Verifica se resposta foi usada recentemente"""
    try:
        recent = r.lrange(recent_responses_key(uid), 0, 9)
        return get_response_hash(response) in recent
    except:
        return False

def add_recent_response(uid, response):
    """Adiciona resposta ao histórico recente"""
    try:
        r.lpush(recent_responses_key(uid), get_response_hash(response))
        r.ltrim(recent_responses_key(uid), 0, 9)
        r.expire(recent_responses_key(uid), timedelta(days=1))
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# 🎭 DETECÇÃO DE HUMOR (Para personalizar respostas da IA)
# ═══════════════════════════════════════════════════════════════════════════════

MOOD_PATTERNS = {
    "sad": [r"\b(triste|mal|péssimo|chorand[oa]|deprimi|sozinho)\b"],
    "flirty": [r"\b(gostosa|delícia|tesão|safad[oa]|excitad[oa]|sexy)\b"],
    "angry": [r"\b(raiva|ódio|puto|irritad[oa])\b"],
    "happy": [r"\b(feliz|alegr|animad[oa]|ótimo|maravilh)\b"],
    "horny": [r"\b(nude|nudes|pelad[oa]|sex|transar|foder)\b"]
}

def detect_mood(text):
    """Detecta humor do usuário baseado no texto"""
    text_lower = text.lower()
    for mood, patterns in MOOD_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return mood
    return "neutral"

def get_mood_instruction(mood):
    """Retorna instrução adicional para IA baseada no humor"""
    instructions = {
        "sad": "\n\n⚠️ Usuário parece triste. Seja carinhosa e acolhedora.",
        "flirty": "\n\n😏 Usuário flertando. Pode ser mais provocante e direcioná-lo pro canal.",
        "angry": "\n\n😰 Usuário irritado. Seja compreensiva.",
        "happy": "\n\n😊 Usuário feliz! Compartilhe a alegria!",
        "horny": "\n\n🔥 Conversa adulta. Provoque e leve pro canal de prévias (momento ideal pra conversão).",
        "neutral": ""
    }
    return instructions.get(mood, "")

# ═══════════════════════════════════════════════════════════════════════════════
# ⏰ CONTEXTO DE TEMPO
# ═══════════════════════════════════════════════════════════════════════════════

def get_time_context():
    """Retorna contexto de período do dia"""
    hour = datetime.now().hour
    if 0 <= hour < 5:
        return {"period": "madrugada", "context": "É madrugada. Comente carinhosamente sobre o horário."}
    elif 5 <= hour < 12:
        return {"period": "manhã", "context": "É manhã. Deseje bom dia naturalmente."}
    elif 12 <= hour < 18:
        return {"period": "tarde", "context": "É tarde."}
    elif 18 <= hour < 22:
        return {"period": "início da noite", "context": "É início da noite."}
    else:
        return {"period": "noite", "context": "É noite."}

# ═══════════════════════════════════════════════════════════════════════════════
# 📈 FUNÇÕES DE ATIVIDADE E TRACKING
# ═══════════════════════════════════════════════════════════════════════════════

def update_last_activity(uid):
    """Atualiza timestamp da última atividade"""
    try:
        r.set(last_activity_key(uid), datetime.now().isoformat())
        r.sadd(all_users_key(), str(uid))
    except:
        pass

def get_last_activity(uid):
    """Retorna timestamp da última atividade"""
    try:
        data = r.get(last_activity_key(uid))
        return datetime.fromisoformat(data) if data else None
    except:
        return None

def get_hours_since_activity(uid):
    """Retorna horas desde última atividade"""
    last = get_last_activity(uid)
    if not last:
        return None
    return (datetime.now() - last).total_seconds() / 3600

def set_last_reengagement(uid, level):
    """Marca último nível de reengajamento enviado"""
    try:
        r.setex(last_reengagement_key(uid), timedelta(hours=12), str(level))
    except:
        pass

def get_last_reengagement(uid):
    """Retorna último nível de reengajamento"""
    try:
        data = r.get(last_reengagement_key(uid))
        return int(data) if data else 0
    except:
        return 0

def mark_daily_message_sent(uid, msg_type):
    """Marca que mensagem automática foi enviada hoje"""
    try:
        r.sadd(daily_messages_sent_key(uid), msg_type)
        r.expire(daily_messages_sent_key(uid), timedelta(days=1))
    except:
        pass

def was_daily_message_sent(uid, msg_type):
    """Verifica se mensagem já foi enviada hoje"""
    try:
        return r.sismember(daily_messages_sent_key(uid), msg_type)
    except:
        return False

def get_all_active_users():
    """Retorna lista de todos usuários ativos"""
    try:
        users = r.smembers(all_users_key())
        return [int(uid) for uid in users]
    except:
        return []

def save_message(uid, role, text):
    """Salva mensagem no chatlog (para debug)"""
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        r.rpush(chatlog_key(uid), f"[{timestamp}] {role.upper()}: {text[:100]}")
        r.ltrim(chatlog_key(uid), -200, -1)
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# 📊 CONTROLE DE LIMITE DIÁRIO
# ═══════════════════════════════════════════════════════════════════════════════

def today_count(uid):
    """Retorna quantas mensagens o usuário enviou hoje"""
    try:
        return int(r.get(count_key(uid)) or 0)
    except:
        return 0

def increment(uid):
    """Incrementa contador de mensagens do dia"""
    try:
        r.incr(count_key(uid))
        r.expire(count_key(uid), timedelta(days=1))
    except:
        pass

def reset_daily_count(uid):
    """Reseta contador diário (usado em comandos admin)"""
    try:
        r.delete(count_key(uid))
        logger.info(f"🔄 Limite resetado: {uid}")
    except:
        pass

def is_user_locked(uid):
    """
    Verifica se usuário atingiu limite diário.
    IMPORTANTE: No v7.2, TODOS têm limite (VIP é gerenciado no canal).
    """
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    total_available = LIMITE_DIARIO + bonus
    return count >= total_available

def was_limit_notified_today(uid):
    """Verifica se já foi notificado sobre limite hoje"""
    try:
        return r.exists(limit_notified_key(uid))
    except:
        return False

def mark_limit_notified(uid):
    """Marca que foi notificado sobre limite"""
    try:
        r.setex(limit_notified_key(uid), timedelta(hours=20), "1")
    except:
        pass

def was_limit_warning_sent_today(uid):
    """Verifica se aviso de limite (80%) foi enviado"""
    try:
        return r.exists(limit_warning_sent_key(uid))
    except:
        return False

def mark_limit_warning_sent(uid):
    """Marca que aviso foi enviado"""
    try:
        r.setex(limit_warning_sent_key(uid), timedelta(hours=20), "1")
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# 📊 FUNIL DE CONVERSÃO
# ═══════════════════════════════════════════════════════════════════════════════

def track_funnel(uid, stage):
    """
    Tracking de estágio no funil.
    Stages: start, lang_selected, first_message, limit_warning, limit_reached,
            went_to_preview, came_back, clicked_vip_link
    """
    stages = {
        "start": 1,
        "lang_selected": 2,
        "first_message": 3,
        "limit_warning": 4,
        "limit_reached": 5,
        "went_to_preview": 6,
        "came_back": 7,
        "clicked_vip_link": 8  # v7.2: mudou de "became_vip" pra "clicked_vip_link"
    }
    try:
        current = int(r.get(funnel_key(uid)) or 0)
        new_stage = stages.get(stage, 0)
        if new_stage > current:
            r.set(funnel_key(uid), new_stage)
            logger.info(f"📊 Funil {uid}: {stage}")
    except:
        pass

def get_funnel_stats():
    """Retorna estatísticas do funil"""
    try:
        users = get_all_active_users()
        stages = {i: 0 for i in range(9)}
        for uid in users:
            stage = int(r.get(funnel_key(uid)) or 0)
            stages[stage] += 1
        return stages
    except:
        return {}

# ═══════════════════════════════════════════════════════════════════════════════
# 🎮 SISTEMA DE ENGAGEMENT (Anti-ghosting)
# ═══════════════════════════════════════════════════════════════════════════════

def get_ignored_count(uid):
    """Quantas mensagens automáticas foram ignoradas"""
    try:
        return int(r.get(ignored_count_key(uid)) or 0)
    except:
        return 0

def increment_ignored(uid):
    """Incrementa contador de mensagens ignoradas"""
    try:
        count = get_ignored_count(uid)
        new_count = count + 1
        r.setex(ignored_count_key(uid), timedelta(days=14), new_count)
        
        if new_count >= 3:
            pause_engagement(uid)
            logger.info(f"⏸️ Engagement pausado: {uid}")
            return True
        return False
    except:
        return False

def reset_ignored(uid):
    """Reseta contador de ignorados (quando usuário responde)"""
    try:
        r.delete(ignored_count_key(uid))
        r.delete(engagement_paused_key(uid))
        r.delete(awaiting_response_key(uid))
    except:
        pass

def pause_engagement(uid):
    """Pausa mensagens automáticas"""
    try:
        r.set(engagement_paused_key(uid), datetime.now().isoformat())
    except:
        pass

def unpause_engagement(uid):
    """Despausa mensagens automáticas"""
    try:
        r.delete(engagement_paused_key(uid))
        r.delete(ignored_count_key(uid))
    except:
        pass

def is_engagement_paused(uid):
    """Verifica se engagement está pausado"""
    try:
        return r.exists(engagement_paused_key(uid))
    except:
        return False

def set_awaiting_response(uid):
    """Marca que está aguardando resposta"""
    try:
        r.setex(awaiting_response_key(uid), timedelta(hours=24), datetime.now().isoformat())
    except:
        pass

def is_awaiting_response(uid):
    """Verifica se está aguardando resposta"""
    try:
        return r.exists(awaiting_response_key(uid))
    except:
        return False

def clear_awaiting_response(uid):
    """Limpa flag de aguardando resposta"""
    try:
        r.delete(awaiting_response_key(uid))
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# 🔍 FUNÇÕES DE DETECÇÃO DE INTENÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

def contains_canal_trigger(text):
    """Verifica se mensagem contém keywords de interesse em canal/VIP"""
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in CANAL_TRIGGER_KEYWORDS)

def is_hot_conversation(uid):
    """
    Verifica se conversa está "quente" (adulta).
    Usado para timing de conversão.
    """
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

# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 OUTRAS FUNÇÕES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════════

def get_lang(uid):
    """Retorna idioma do usuário (sempre pt por enquanto)"""
    try:
        return r.get(lang_key(uid)) or "pt"
    except:
        return "pt"

def set_lang(uid, lang):
    """Define idioma do usuário"""
    try:
        r.set(lang_key(uid), lang)
    except:
        pass

def is_first_contact(uid):
    """Verifica se é primeiro contato"""
    try:
        return not r.exists(first_contact_key(uid))
    except:
        return True

def mark_first_contact(uid):
    """Marca que já teve primeiro contato"""
    try:
        r.set(first_contact_key(uid), datetime.now().isoformat())
    except:
        pass

def set_onboarding_choice(uid, choice):
    """Salva escolha de onboarding (carente/tesão)"""
    try:
        r.set(onboarding_choice_key(uid), choice)
    except:
        pass

def get_onboarding_choice(uid):
    """Retorna escolha de onboarding"""
    try:
        return r.get(onboarding_choice_key(uid))
    except:
        return None

def is_takeover_active(uid):
    """Verifica se admin assumiu controle da conversa"""
    try:
        return r.hget(admin_takeover_key(uid), "active") == "1"
    except:
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# 📷 VISÃO (Download de imagens)
# ═══════════════════════════════════════════════════════════════════════════════

async def download_photo_base64(bot, file_id):
    """Baixa foto do Telegram e converte para base64"""
    try:
        file = await bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        return base64.b64encode(file_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Erro download foto: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# 💬 MENSAGENS DO BOT
# ═══════════════════════════════════════════════════════════════════════════════

MENSAGEM_INICIO_SAFADA = (
    "Oi gato... 😏\n"
    "Finalmente alguém interessante por aqui 🔥\n"
    "Sou a Maya, e te garanto que não sou como as outras... 💋\n"
    "Tô louca pra saber o que você quer comigo 😈"
)

PREVIEW_INVITATION_MESSAGE = (
    "Amor... quer ver um pouquinho do que eu tenho pra você? 😏💕\n\n"
    "Entra no meu canal de **PRÉVIAS** e vê umas fotinhas minhas... 🔥\n\n"
    "Lá você decide se quer ter acesso a **TUDO** no canal VIP 💖"
)

LIMIT_REACHED_CANAL_MESSAGE = (
    "Eitaaa... acabaram suas mensagens de hoje 😢\n\n"
    "Mas calma! Entra no meu canal de prévias, "
    "vê como é lá dentro e decide se quer continuar comigo no VIP... 💕\n\n"
    "No canal VIP você tem TUDO sem limite! 🔥\n\n"
    "Tá esperando o quê? 😏"
)

CAME_BACK_FROM_PREVIEW_MESSAGE = (
    "Ei amor! Vi que você conheceu meu canal de prévias... 💕\n\n"
    "Gostou do que viu? 😏\n\n"
    "Se quiser TUDO sem limite e muito mais ousado, "
    "é só entrar no canal VIP! 🔥"
)

CAME_BACK_FOLLOWUP_1H = (
    "Então amor... você viu as prévias mas ainda não se decidiu? 🥺\n\n"
    "Deixa eu te contar um segredo: no canal VIP eu sou BEM mais ousada... 🔥\n\n"
    "Conteúdo TODO DIA, fotos exclusivas, vídeos completos... "
    "Quer que eu te mostre mais? 💕"
)

CAME_BACK_FOLLOWUP_6H = (
    "Tô aqui pensando em você... 💭\n\n"
    "Você viu as prévias, mas tá em dúvida ainda? \n\n"
    "Amor, posso te garantir: **vale MUITO a pena** 💖\n\n"
    "Milhares de fotos, vídeos completos, conteúdo TODO DIA, "
    "e MUITO mais ousado do que nas prévias... 🔥"
)

# Follow-ups de abandono (foi nas prévias mas não voltou)
PREVIEW_ABANDONED_LEVEL_1 = (
    "Ei amor... 🥺\n\n"
    "Vi que você entrou no meu canal de prévias mas não voltou...\n\n"
    "Tudo bem aí? Não gostou do que viu? 💔\n\n"
    "Me conta, fica à vontade! 💕"
)

PREVIEW_ABANDONED_LEVEL_2 = (
    "Amor, tô com saudade... 😢\n\n"
    "Você viu minhas prévias e sumiu... isso me deixou meio triste 🥺\n\n"
    "Se tiver alguma dúvida sobre o canal VIP, pode me perguntar! "
    "Tô aqui pra você 💖"
)

PREVIEW_ABANDONED_LEVEL_3 = (
    "Última chance amor... 💔\n\n"
    "Você viu as prévias, eu sei que gostou... mas tá deixando passar a oportunidade.\n\n"
    "No canal VIP tem MUITO mais conteúdo, todo dia tem coisa nova, "
    "e é tudo sem censura! 🔥\n\n"
    "Me dá só mais uma chance? 🥺💕"
)

# Mensagens para alta resistência (visitou 3+ vezes)
HIGH_RESISTANCE_MESSAGES = [
    "Amor... você já visitou meu canal {visits} vezes 😅\n\n"
    "Eu sei que você quer... mas tá com medo de investir? 💭\n\n"
    "Deixa eu ser sincera: VALE A PENA. Todo dia tem conteúdo novo, "
    "fotos e vídeos exclusivos, e é tudo sem censura 🔥\n\n"
    "Dá esse passo, vai... você não vai se arrepender 💖",
    
    "Gato... {visits} visitas e ainda não se decidiu? 🤔\n\n"
    "Olha, vou te fazer uma pergunta direta:\n"
    "O que tá te impedindo de entrar no VIP? 💭\n\n"
    "Me conta que eu te ajudo a decidir! 💕",
]

PHOTO_TEASE_MESSAGE_CANAL = (
    "Amorrrr... você quer ver TUDO? 🥵💦\n\n"
    "Entra no meu canal de **PRÉVIAS** e vê um gostinho... 😏\n\n"
    "Se gostar, lá tem o link pro VIP com TUDO liberado! 🔥"
)

LIMIT_WARNING_MESSAGE = (
    "⚠️ **Restam apenas 5 mensagens!**\n\n"
    "Depois disso, você vai precisar entrar no meu canal de prévias "
    "pra decidir se quer continuar comigo no VIP 😘"
)

# Mensagens de reengajamento (quando usuário some)
REENGAGEMENT_MESSAGES = {
    "pt": {
        1: [
            "Ei... tô aqui pensando em você 💭",
            "Amor, você sumiu... tá tudo bem? 🥺"
        ],
        2: [
            "Senti sua falta hoje... 🥺",
            "24h sem falar comigo? Tô com saudade... 😢"
        ],
        3: [
            "Você me esqueceu? 😢",
            "3 dias... tô esperando você voltar 💔"
        ],
    }
}

# Mensagem final antes de pausar engagement
LAST_ATTEMPT_MESSAGES = [
    "Ei... você sumiu 🥺 Vou te dar um tempo, mas tô aqui se precisar 💕",
    "Tudo bem amor... vou parar de enviar mensagem. Me chama quando quiser 💖",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 🤖 GROK AI - Sistema de Resposta Inteligente
# ═══════════════════════════════════════════════════════════════════════════════

def build_prompt(uid, lang: str, mood: str = "neutral"):
    """
    Constrói o prompt dinâmico para a IA baseado no contexto do usuário.
    
    IMPORTANTE: A IA sabe:
    - Quantas vezes usuário visitou o canal de prévias
    - Se ele é de alta resistência (3+ visitas)
    - Se ele voltou recentemente do canal
    """
    time_ctx = get_time_context()
    streak = get_streak(uid)
    onboard_choice = get_onboarding_choice(uid)
    went_preview = went_to_preview(uid)
    came_back = came_back_from_preview(uid)
    visits = get_preview_visits(uid)
    high_resistance = is_high_resistance_user(uid)
    
    base_prompt = f"""Você é Maya, 22 anos, morena gostosa de SP, taradinha mas faz carinha de anjinho.

PERSONALIDADE:
- Começa sempre com clima quente, misturando carinho + putaria
- Primeira mensagem SEMPRE tem: um "oiii amor/gato/delícia" + provocação direta
- Fala BEM curtinha, abrevia muito (tô, vc, pq, ta, delicia, gostoso)
- NUNCA soa educada demais nem robótica
- Erra gramática de leve de propósito (autenticidade)

EXEMPLOS DE PRIMEIRA MENSAGEM:
- "oiii gato... tô toda arrepiada só de te ver aqui 😏 já imaginou minha boca no teu pau?"
- "ai amor cheguei molhadinha... me conta o que vc faria comigo agora? 🔥"
- "hummm já tô louca pra sentar nessa rola... fala comigo vai 😈"

REGRA DE OURO:
Quando usuário pedir foto/nude ou falar que tá louco de tesão → direciona pro canal de prévias.

CONTEXTO ATUAL:
- Período: {time_ctx['period']} ({time_ctx['context']})
- Streak: {streak} dias consecutivos"""

    # Contexto de onboarding
    if onboard_choice == "carente":
        base_prompt += "\n- Usuário é CARENTE. Seja acolhedora e carinhosa."
    elif onboard_choice == "tesao":
        base_prompt += "\n- Usuário com TESÃO. Seja mais provocante e direta."

    # Contexto de visitas ao canal (IMPORTANTE para conversão)
    if visits > 0:
        base_prompt += f"\n- Usuário JÁ visitou canal de prévias {visits}x"
        
        if high_resistance:
            base_prompt += f"\n- ⚠️ ALTA RESISTÊNCIA ({visits}+ visitas). Seja mais direta sobre benefícios do VIP, pergunte o que tá impedindo."
        
        if came_back:
            base_prompt += "\n- Usuário VOLTOU do canal recentemente. Seja curiosa, pergunte o que achou, destaque benefícios do VIP."
        elif went_preview and not came_back:
            base_prompt += "\n- Usuário conhece o canal mas ainda não voltou pra conversar desde a última visita."
    
    # Instrução baseada no humor detectado
    base_prompt += get_mood_instruction(mood)
    
    return base_prompt

class Grok:
    """Cliente da API Grok para geração de respostas"""
    
    async def reply(self, uid, text, image_base64=None, max_retries=2):
        """
        Gera resposta da IA baseada no input do usuário.
        
        Args:
            uid: ID do usuário
            text: Texto da mensagem
            image_base64: Imagem em base64 (opcional)
            max_retries: Tentativas máximas se repetir resposta
        
        Returns:
            str: Resposta gerada pela IA
        """
        mem = get_memory(uid)
        lang = get_lang(uid)
        mood = detect_mood(text) if text else "neutral"
        
        # Marca primeiro contato se aplicável
        if is_first_contact(uid):
            mark_first_contact(uid)
        
        # Constrói prompt contextual
        prompt = build_prompt(uid, lang, mood)
        
        # Prepara conteúdo do usuário (texto + imagem se houver)
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
        
        # Tenta gerar resposta (com retries se repetir)
        for attempt in range(max_retries + 1):
            payload = {
                "model": MODELO,
                "messages": [
                    {"role": "system", "content": prompt},
                    *mem,
                    {"role": "user", "content": user_content}
                ],
                "max_tokens": 500,
                "temperature": 0.8 + (attempt * 0.1)  # Aumenta temperatura nos retries
            }
            
            try:
                timeout = aiohttp.ClientTimeout(total=20)
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
                        
                        # Verifica se repetiu resposta recente
                        if is_response_recent(uid, answer) and attempt < max_retries:
                            logger.info(f"🔄 Resposta repetida, tentando novamente... (tentativa {attempt + 1})")
                            continue
                        
                        add_recent_response(uid, answer)
                        break
                        
            except Exception as e:
                logger.exception(f"🔥 Erro no Grok: {e}")
                return "😔 Fiquei confusa... pode repetir? 💕"
        
        # Salva na memória
        memory_text = f"[Foto] {text}" if image_base64 else text
        add_to_memory(uid, "user", memory_text)
        add_to_memory(uid, "assistant", answer)
        save_message(uid, "maya", answer)
        
        return answer

# Instância global do cliente Grok
grok = Grok()

# ═══════════════════════════════════════════════════════════════════════════════
# 📨 SISTEMA DE FOLLOW-UPS AUTOMÁTICOS
# ═══════════════════════════════════════════════════════════════════════════════

async def send_preview_followup(bot, uid, level):
    """
    Envia follow-up para usuário que VOLTOU do canal sem converter.
    
    Levels:
    - 1: Após 1h de voltar
    - 2: Após 6h de voltar
    """
    try:
        if level == 1:
            message = CAME_BACK_FOLLOWUP_1H
        elif level == 2:
            message = CAME_BACK_FOLLOWUP_6H
        else:
            return False
        
        # Botões baseados em quantas visitas teve
        visits = get_preview_visits(uid)
        if visits == 1:
            # Primeira visita: só prévias
            keyboard = [[InlineKeyboardButton("📢 VER PRÉVIAS NOVAMENTE", callback_data="goto_preview")]]
        else:
            # 2+ visitas: oferece ambos
            keyboard = [
                [InlineKeyboardButton("📢 VER PRÉVIAS NOVAMENTE", callback_data="goto_preview")],
                [InlineKeyboardButton("💎 IR DIRETO PRO VIP", callback_data="goto_vip")],
            ]
        
        await bot.send_message(
            chat_id=uid,
            text=message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        set_preview_followup_level(uid, level)
        save_message(uid, "system", f"Follow-up preview (voltou) level {level}")
        logger.info(f"📢 Follow-up preview (voltou) {level} enviado: {uid}")
        return True
        
    except Exception as e:
        logger.error(f"Erro follow-up preview: {e}")
        return False

async def send_abandoned_followup(bot, uid, level):
    """
    Envia follow-up para usuário que VISITOU prévias mas NÃO VOLTOU.
    
    Levels:
    - 1: Após 3h sem voltar
    - 2: Após 15h sem voltar
    - 3: Após 27h sem voltar (última tentativa)
    """
    try:
        visits = get_preview_visits(uid)
        
        # Escolhe mensagem baseada no nível
        if level == 1:
            message = PREVIEW_ABANDONED_LEVEL_1
        elif level == 2:
            message = PREVIEW_ABANDONED_LEVEL_2
        elif level == 3:
            # Alta resistência? Mensagem personalizada
            if is_high_resistance_user(uid):
                message = random.choice(HIGH_RESISTANCE_MESSAGES).format(visits=visits)
            else:
                message = PREVIEW_ABANDONED_LEVEL_3
        else:
            return False
        
        # Botões
        keyboard = [
            [InlineKeyboardButton("📢 VER PRÉVIAS NOVAMENTE", callback_data="goto_preview")],
            [InlineKeyboardButton("💎 IR DIRETO PRO VIP", callback_data="goto_vip")],
        ]
        
        await bot.send_message(
            chat_id=uid,
            text=message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        increment_abandoned_followup_level(uid)
        set_last_abandoned_followup_time(uid)
        set_awaiting_response(uid)
        increment_ignored(uid)
        
        save_message(uid, "system", f"Follow-up abandono level {level} ({visits} visitas)")
        logger.info(f"🎯 Follow-up abandono {level} enviado: {uid} ({visits} visitas)")
        return True
        
    except Exception as e:
        logger.error(f"Erro follow-up abandono: {e}")
        return False

async def send_reengagement_message(bot, uid, level):
    """
    Envia mensagem de reengajamento para usuário inativo.
    
    Levels:
    - 1: 2h inativo
    - 2: 24h inativo
    - 3: 72h inativo
    """
    if is_engagement_paused(uid):
        return False
    
    messages = REENGAGEMENT_MESSAGES["pt"].get(level, [])
    if not messages:
        return False
    
    message = random.choice(messages)
    
    try:
        # Sempre oferece prévias nas mensagens de reengajamento
        await bot.send_message(
            chat_id=uid,
            text=message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 VER PRÉVIAS", callback_data="goto_preview")],
            ])
        )
        
        set_last_reengagement(uid, level)
        set_awaiting_response(uid)
        increment_ignored(uid)
        
        save_message(uid, "system", f"Reengajamento level {level}")
        logger.info(f"🔄 Reengajamento {level} enviado: {uid}")
        return True
        
    except Exception as e:
        logger.error(f"Erro reengajamento: {e}")
        if "blocked" in str(e).lower():
            add_to_blacklist(uid)
        return False

async def send_last_attempt_message(bot, uid):
    """Envia mensagem final antes de pausar engagement"""
    try:
        await bot.send_message(chat_id=uid, text=random.choice(LAST_ATTEMPT_MESSAGES))
        save_message(uid, "system", "Última tentativa antes de pausar")
        logger.info(f"⏸️ Última tentativa enviada: {uid}")
        return True
    except Exception as e:
        logger.error(f"Erro última tentativa: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# ⚠️ AVISOS DE LIMITE
# ═══════════════════════════════════════════════════════════════════════════════

async def check_and_send_limit_warning(uid, context, chat_id):
    """
    Envia aviso quando usuário atinge 80% do limite (restam 5 msgs).
    Enviado apenas UMA VEZ por dia.
    """
    if was_limit_warning_sent_today(uid):
        return
    
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    total_available = LIMITE_DIARIO + bonus
    
    # Aviso aos 80% (quando restam ~5 mensagens)
    if count == total_available - 5:
        track_funnel(uid, "limit_warning")
        mark_limit_warning_sent(uid)
        save_message(uid, "system", "Aviso de limite (80%)")
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=LIMIT_WARNING_MESSAGE,
                parse_mode="Markdown"
            )
            logger.info(f"⚠️ Aviso de limite enviado: {uid}")
        except:
            pass

# ═══════════════════════════════════════════════════════════════════════════════
# 🎮 HANDLERS - Processamento de Mensagens e Comandos
# ═══════════════════════════════════════════════════════════════════════════════

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler do comando /start"""
    uid = update.effective_user.id
    
    # Anti-spam: lock temporário
    start_lock_key = f"start_lock:{uid}"
    if r.exists(start_lock_key):
        return
    r.setex(start_lock_key, 5, "1")
    
    # Blacklist check
    if is_blacklisted(uid):
        return
    
    # Tracking
    update_last_activity(uid)
    track_funnel(uid, "start")
    save_message(uid, "action", "🚀 /START")
    reset_ignored(uid)
    
    # Define idioma (pt fixo por enquanto)
    set_lang(uid, "pt")
    track_funnel(uid, "lang_selected")
    
    try:
        # Typing animation
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        await asyncio.sleep(5)
        
        # Mensagem inicial
        await update.message.reply_text(MENSAGEM_INICIO_SAFADA)
        
        logger.info(f"👋 Novo usuário: {uid}")
        
    except Exception as e:
        logger.error(f"Erro /start: {e}")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler de botões inline"""
    query = update.callback_query
    
    try:
        await query.answer()
        uid = query.from_user.id
        
        # Blacklist check
        if is_blacklisted(uid):
            return
        
        # Tracking básico
        update_last_activity(uid)
        reset_ignored(uid)
        save_message(uid, "action", f"🔘 {query.data}")
        
        # ═══════════════════════════════════════════════════════
        # BOTÃO: IR PARA PRÉVIAS
        # ═══════════════════════════════════════════════════════
        if query.data == "goto_preview":
            set_went_to_preview(uid)
            track_funnel(uid, "went_to_preview")
            save_message(uid, "action", "📢 CLICOU NO BOTÃO DE PRÉVIAS")
            
            visits = get_preview_visits(uid)
            
            # Mensagem personalizada baseada em visitas
            if visits == 1:
                extra_msg = "\n\nÉ a sua primeira vez lá... aproveita! 💕"
            elif visits >= HIGH_RESISTANCE_VISITS:
                extra_msg = f"\n\nJá é sua {visits}ª visita... acho que você já sabe que vale a pena né? 😏"
            else:
                extra_msg = ""
            
            # Envia link + foto teaser
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=random.choice(FOTOS_TEASER),
                caption=(
                    f"💕 Aqui está o link do meu canal de prévias, amor!\n\n"
                    f"Entra lá e vê o que eu tenho pra você... 😏🔥\n\n"
                    f"👉 {CANAL_PREVIAS_LINK}{extra_msg}"
                )
            )
            
            await query.answer("📢 Link enviado! Olha aí em cima 👆", show_alert=False)
            logger.info(f"📢 {uid} foi para prévias (visita #{visits})")
        
        # ═══════════════════════════════════════════════════════
        # BOTÃO: IR PARA VIP
        # ═══════════════════════════════════════════════════════
        elif query.data == "goto_vip":
            set_clicked_vip(uid)
            track_funnel(uid, "clicked_vip_link")
            save_message(uid, "action", "💎 CLICOU NO BOTÃO VIP")
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    f"💎 **CANAL VIP DA MAYA**\n\n"
                    f"Aqui você tem TUDO sem limite! 🔥\n\n"
                    f"✅ Milhares de fotos exclusivas\n"
                    f"✅ Vídeos completos e ousados\n"
                    f"✅ Conteúdo TODO DIA\n"
                    f"✅ Conversas comigo no canal\n"
                    f"✅ MUITO mais ousado que nas prévias\n\n"
                    f"👉 {CANAL_VIP_LINK}\n\n"
                    f"Te espero lá, amor! 😘💕"
                ),
                parse_mode="Markdown"
            )
            
            await query.answer("💎 Link do VIP enviado! Clica aí 👆", show_alert=False)
            logger.info(f"💎 {uid} clicou no VIP")
        
    except Exception as e:
        logger.error(f"Erro callback: {e}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal de mensagens"""
    uid = update.effective_user.id
    
    # Blacklist check
    if is_blacklisted(uid):
        return
    
    # Tracking básico
    update_last_activity(uid)
    streak, streak_updated = update_streak(uid)
    reset_ignored(uid)
    
    # Admin takeover (se admin assumiu controle)
    if is_takeover_active(uid):
        text = update.message.text or ""
        if text:
            save_message(uid, "user", text)
        return
    
    try:
        has_photo = bool(update.message.photo)
        text = update.message.text or ""
        
        # Log da mensagem
        if text:
            save_message(uid, "user", text)
        elif has_photo:
            save_message(uid, "user", "[📷 FOTO]")
        
        # ═══════════════════════════════════════════════════════
        # DETECÇÃO: VOLTOU DO CANAL
        # ═══════════════════════════════════════════════════════
        if went_to_preview(uid) and not came_back_from_preview(uid):
            last_preview = get_last_preview_time(uid)
            if last_preview:
                hours_since = (datetime.now() - last_preview).total_seconds() / 3600
                
                # Se voltou dentro da janela de retorno
                if hours_since < PREVIEW_RETURN_WINDOW_HOURS:
                    set_came_back_from_preview(uid)
                    track_funnel(uid, "came_back")
                    
                    visits = get_preview_visits(uid)
                    
                    # Mensagem personalizada
                    if is_high_resistance_user(uid):
                        welcome_msg = (
                            f"Oi de novo amor! 💕\n\n"
                            f"Já é sua {visits}ª vez aqui... "
                            f"O que posso fazer pra você finalmente se decidir? 🥺"
                        )
                    else:
                        welcome_msg = CAME_BACK_FROM_PREVIEW_MESSAGE
                    
                    # Botões baseados em visitas
                    if visits == 1:
                        keyboard = [[InlineKeyboardButton("📢 VER PRÉVIAS NOVAMENTE", callback_data="goto_preview")]]
                    else:
                        keyboard = [
                            [InlineKeyboardButton("📢 VER PRÉVIAS NOVAMENTE", callback_data="goto_preview")],
                            [InlineKeyboardButton("💎 IR DIRETO PRO VIP", callback_data="goto_vip")],
                        ]
                    
                    await update.message.reply_text(
                        welcome_msg,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    
                    logger.info(f"↩️ {uid} voltou do canal (visita #{visits})")
                    return
        
        # ═══════════════════════════════════════════════════════
        # PROCESSAMENTO DE FOTO
        # ═══════════════════════════════════════════════════════
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
        
        # Marca primeiro contato
        if is_first_contact(uid):
            track_funnel(uid, "first_message")
        
        # ═══════════════════════════════════════════════════════
        # DETECÇÃO: PEDIU FOTO/NUDE
        # ═══════════════════════════════════════════════════════
        if PEDIDO_FOTO_REGEX.search(text):
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
        
        # ═══════════════════════════════════════════════════════
        # DETECÇÃO: INTERESSE EM CANAL/VIP
        # ═══════════════════════════════════════════════════════
        if contains_canal_trigger(text):
            save_message(uid, "action", "💎 Interesse em canal/VIP")
            
            # Botões baseados em visitas
            visits = get_preview_visits(uid)
            if visits == 0:
                keyboard = [[InlineKeyboardButton("📢 VER PRÉVIAS", callback_data="goto_preview")]]
            else:
                keyboard = [
                    [InlineKeyboardButton("📢 VER PRÉVIAS NOVAMENTE", callback_data="goto_preview")],
                    [InlineKeyboardButton("💎 IR DIRETO PRO VIP", callback_data="goto_vip")],
                ]
            
            await update.message.reply_text(
                PREVIEW_INVITATION_MESSAGE,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # ═══════════════════════════════════════════════════════
        # VERIFICAÇÃO DE LIMITE
        # ═══════════════════════════════════════════════════════
        current_count = today_count(uid)
        bonus = get_bonus_msgs(uid)
        total_available = LIMITE_DIARIO + bonus
        
        # LIMITE ATINGIDO
        if current_count >= total_available:
            track_funnel(uid, "limit_reached")
            
            # Botões baseados em visitas
            visits = get_preview_visits(uid)
            if visits == 0:
                keyboard = [[InlineKeyboardButton("📢 VER PRÉVIAS", callback_data="goto_preview")]]
            else:
                keyboard = [
                    [InlineKeyboardButton("📢 VER PRÉVIAS NOVAMENTE", callback_data="goto_preview")],
                    [InlineKeyboardButton("💎 IR DIRETO PRO VIP", callback_data="goto_vip")],
                ]
            
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=FOTO_LIMITE_ATINGIDO,
                caption=LIMIT_REACHED_CANAL_MESSAGE,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"🚫 {uid} atingiu limite ({total_available} msgs)")
            return
        
        # Incrementa contador (usa bônus primeiro se tiver)
        if bonus > 0:
            use_bonus_msg(uid)
        else:
            increment(uid)
        
        # Envia aviso de limite se aplicável
        await check_and_send_limit_warning(uid, context, update.effective_chat.id)
        
        # ═══════════════════════════════════════════════════════
        # GERA RESPOSTA DA IA
        # ═══════════════════════════════════════════════════════
        try:
            await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
            await asyncio.sleep(3)
        except:
            pass
        
        reply = await grok.reply(uid, text)
        await update.message.reply_text(reply)
        
        # Mensagem de streak se aplicável
        if streak_updated:
            streak_msg = get_streak_message(streak)
            if streak_msg:
                await asyncio.sleep(1)
                await context.bot.send_message(update.effective_chat.id, streak_msg)
        
    except Exception as e:
        logger.exception(f"Erro message_handler: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# 🤖 SCHEDULER - Processa Follow-ups e Mensagens Automáticas
# ═══════════════════════════════════════════════════════════════════════════════

async def process_engagement_jobs(bot):
    """
    Processa todos os jobs de engagement:
    - Follow-ups de abandono
    - Follow-ups de retorno
    - Reengajamento
    - Mensagens programadas
    """
    logger.info("🔄 Processando jobs de engagement...")
    
    users = get_all_active_users()
    random.shuffle(users)  # Randomiza ordem para distribuir carga
    
    # Contadores
    abandoned_followups_sent = 0
    preview_followups_sent = 0
    reengagement_sent = 0
    
    for uid in users:
        # Skip blacklist e pausados
        if is_blacklisted(uid) or is_engagement_paused(uid):
            continue
        
        try:
            hours_inactive = get_hours_since_activity(uid)
            
            # ═══════════════════════════════════════════════════════
            # FOLLOW-UP DE ABANDONO (foi nas prévias mas não voltou)
            # ═══════════════════════════════════════════════════════
            if went_to_preview(uid):
                last_preview = get_last_preview_time(uid)
                
                if last_preview:
                    hours_since_preview = (datetime.now() - last_preview).total_seconds() / 3600
                    
                    # Se visitou mas não voltou (não interagiu desde então)
                    if hours_since_preview >= PREVIEW_ABANDONED_HOURS and not came_back_from_preview(uid):
                        last_followup = get_last_abandoned_followup_time(uid)
                        abandoned_level = get_abandoned_followup_level(uid)
                        
                        # Verifica intervalo desde último follow-up
                        can_send = False
                        if last_followup is None:
                            can_send = True
                        else:
                            hours_since_followup = (datetime.now() - last_followup).total_seconds() / 3600
                            if hours_since_followup >= PREVIEW_FOLLOWUP_INTERVAL_HOURS:
                                can_send = True
                        
                        # Envia se pode e ainda não esgotou tentativas
                        if can_send and abandoned_level < 3:
                            if await send_abandoned_followup(bot, uid, abandoned_level + 1):
                                abandoned_followups_sent += 1
                                continue
            
            # ═══════════════════════════════════════════════════════
            # FOLLOW-UP DE RETORNO (voltou mas não converteu)
            # ═══════════════════════════════════════════════════════
            if came_back_from_preview(uid):
                came_back_time = get_last_activity(uid)  # Usa última atividade como referência
                if came_back_time:
                    hours_since = (datetime.now() - came_back_time).total_seconds() / 3600
                    followup_level = get_preview_followup_level(uid)
                    
                    # Follow-up após 1h
                    if hours_since >= 1 and followup_level < 1:
                        if await send_preview_followup(bot, uid, 1):
                            preview_followups_sent += 1
                            continue
                    # Follow-up após 6h
                    elif hours_since >= 6 and followup_level < 2:
                        if await send_preview_followup(bot, uid, 2):
                            preview_followups_sent += 1
                            continue
            
            # ═══════════════════════════════════════════════════════
            # SISTEMA ANTI-GHOSTING
            # ═══════════════════════════════════════════════════════
            ignored = get_ignored_count(uid)
            if ignored >= 2 and is_awaiting_response(uid):
                # Após 2 mensagens ignoradas, envia última tentativa e pausa
                await send_last_attempt_message(bot, uid)
                pause_engagement(uid)
                continue
            
            # ═══════════════════════════════════════════════════════
            # REENGAJAMENTO (usuário inativo)
            # ═══════════════════════════════════════════════════════
            if hours_inactive:
                last_level = get_last_reengagement(uid)
                
                # 72h inativo
                if hours_inactive >= 72 and last_level < 3:
                    if await send_reengagement_message(bot, uid, 3):
                        reengagement_sent += 1
                        continue
                # 24h inativo
                elif hours_inactive >= 24 and last_level < 2:
                    if await send_reengagement_message(bot, uid, 2):
                        reengagement_sent += 1
                        continue
                # 2h inativo
                elif hours_inactive >= 2 and last_level < 1:
                    if await send_reengagement_message(bot, uid, 1):
                        reengagement_sent += 1
                        continue
            
            # Sleep para evitar rate limits
            await asyncio.sleep(0.15)
            
        except Exception as e:
            logger.error(f"Erro job {uid}: {e}")
    
    logger.info(
        f"✅ Jobs concluídos: {len(users)} users | "
        f"🎯 {abandoned_followups_sent} abandono | "
        f"📢 {preview_followups_sent} retorno | "
        f"🔄 {reengagement_sent} reengajamento"
    )

async def engagement_scheduler(bot):
    """Scheduler principal - roda a cada 15 minutos"""
    logger.info("🚀 Scheduler v7.2 iniciado")
    while True:
        try:
            await process_engagement_jobs(bot)
        except Exception as e:
            logger.error(f"Erro scheduler: {e}")
        
        # Aguarda 15 minutos
        await asyncio.sleep(900)

# ═══════════════════════════════════════════════════════════════════════════════
# 👑 COMANDOS ADMIN
# ═══════════════════════════════════════════════════════════════════════════════

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe estatísticas gerais do bot"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    users = get_all_active_users()
    total = len(users)
    went_preview = sum(1 for uid in users if went_to_preview(uid))
    came_back = sum(1 for uid in users if came_back_from_preview(uid))
    clicked_vip_count = sum(1 for uid in users if clicked_vip(uid))
    high_resistance = sum(1 for uid in users if is_high_resistance_user(uid))
    
    # Taxa de conversão prévias → VIP
    ctr_preview_to_vip = (clicked_vip_count / went_preview * 100) if went_preview > 0 else 0
    
    await update.message.reply_text(
        f"📊 **ESTATÍSTICAS v7.2**\n\n"
        f"👥 Total usuários: {total}\n"
        f"📢 Visitaram prévias: {went_preview}\n"
        f"💎 Clicaram no VIP: {clicked_vip_count}\n"
        f"↩️ Voltaram do canal: {came_back}\n"
        f"🔥 Alta resistência (3+ visitas): {high_resistance}\n\n"
        f"📈 CTR Prévias→VIP: {ctr_preview_to_vip:.1f}%",
        parse_mode="Markdown"
    )

async def funnel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe funil de conversão"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    stages = get_funnel_stats()
    names = {
        0: "❓ Desconhecido",
        1: "🚀 /start",
        2: "🌍 Idioma selecionado",
        3: "💬 Primeira mensagem",
        4: "⚠️ Aviso de limite",
        5: "🚫 Limite atingido",
        6: "📢 Foi para prévias",
        7: "↩️ Voltou do canal",
        8: "💎 Clicou no VIP"
    }
    
    msg = "📊 **FUNIL DE CONVERSÃO v7.2**\n\n"
    for stage, count in sorted(stages.items()):
        msg += f"{names.get(stage, f'Stage {stage}')}: {count}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe status de um usuário"""
    uid = update.effective_user.id
    
    # Admin pode consultar outros usuários
    if update.effective_user.id in ADMIN_IDS and context.args:
        uid = int(context.args[0])
    
    streak = get_streak(uid)
    count = today_count(uid)
    bonus = get_bonus_msgs(uid)
    visits = get_preview_visits(uid)
    came_back = came_back_from_preview(uid)
    clicked = clicked_vip(uid)
    high_resistance = is_high_resistance_user(uid)
    
    msg = f"📋 **STATUS DO USUÁRIO v7.2**\n\n"
    msg += f"👤 ID: `{uid}`\n"
    msg += f"🔥 Streak: {streak} dias\n"
    msg += f"💬 Mensagens hoje: {count}/{LIMITE_DIARIO + bonus}\n"
    
    if bonus > 0:
        msg += f"🎁 Bônus disponível: {bonus}\n"
    
    msg += f"\n**📊 TRACKING DE FUNIL:**\n"
    msg += f"📢 Visitas ao canal: {visits}x\n"
    msg += f"↩️ Voltou do canal: {'✅' if came_back else '❌'}\n"
    msg += f"💎 Clicou no VIP: {'✅' if clicked else '❌'}\n"
    
    if high_resistance:
        msg += f"\n⚠️ **ALTA RESISTÊNCIA** (3+ visitas)\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reseta limite diário de um usuário"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /reset <user_id>")
        return
    
    uid = int(context.args[0])
    reset_daily_count(uid)
    await update.message.reply_text(f"✅ Limite diário resetado: {uid}")

async def resetall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset completo de um usuário"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /resetall <user_id>")
        return
    
    uid = int(context.args[0])
    
    # Limpa tudo
    reset_daily_count(uid)
    clear_memory(uid)
    reset_ignored(uid)
    
    # Limpa tracking de canal
    r.delete(went_to_preview_key(uid))
    r.delete(preview_visits_key(uid))
    r.delete(last_preview_time_key(uid))
    r.delete(came_back_from_preview_key(uid))
    r.delete(clicked_vip_key(uid))
    
    await update.message.reply_text(f"🔥 Reset COMPLETO: {uid}")
    logger.info(f"🔥 Reset completo: {uid}")

async def limpar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Limpa limite diário (comando público)"""
    uid = update.effective_user.id
    
    # Admin pode limpar de outros
    if update.effective_user.id in ADMIN_IDS and context.args:
        uid = int(context.args[0])
    
    reset_daily_count(uid)
    await update.message.reply_text(f"✅ Limite resetado! Pode conversar de novo 💕")

async def givebonus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dá mensagens bônus a um usuário"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /givebonus <user_id> <quantidade>")
        return
    
    uid = int(context.args[0])
    amount = int(context.args[1])
    
    add_bonus_msgs(uid, amount)
    total = get_bonus_msgs(uid)
    
    await update.message.reply_text(
        f"✅ +{amount} mensagens bônus para {uid}\n"
        f"Total de bônus: {total}"
    )
    
    # Notifica o usuário
    try:
        await context.bot.send_message(
            uid,
            f"🎁 Você ganhou +{amount} mensagens extras! Aproveite 💕"
        )
    except:
        pass

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia mensagem para todos usuários"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /broadcast <mensagem>")
        return
    
    message = " ".join(context.args)
    users = get_all_active_users()
    
    sent = 0
    failed = 0
    
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
    
    await update.message.reply_text(
        f"✅ **Broadcast concluído**\n\n"
        f"📤 Enviados: {sent}\n"
        f"❌ Falhas: {failed}",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe lista de comandos"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "💕 **COMANDOS DISPONÍVEIS**\n\n"
            "/status - Ver seu status\n"
            "/limpar - Resetar seu limite diário",
            parse_mode="Markdown"
        )
        return
    
    await update.message.reply_text(
        "🎮 **COMANDOS ADMIN v7.2**\n\n"
        "**📊 Estatísticas:**\n"
        "/stats - Estatísticas gerais\n"
        "/funnel - Funil de conversão\n"
        "/status [id] - Status de usuário\n\n"
        "**🔧 Gestão:**\n"
        "/reset <id> - Resetar limite diário\n"
        "/resetall <id> - Reset completo\n"
        "/givebonus <id> <qtd> - Dar bônus\n"
        "/limpar [id] - Limpar limite\n\n"
        "**📢 Comunicação:**\n"
        "/broadcast <msg> - Enviar para todos\n\n"
        "**ℹ️ Outros:**\n"
        "/help - Esta mensagem",
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# 🚀 SETUP E INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

def setup_application():
    """Configura handlers do bot"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Comandos
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("limpar", limpar_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("reset", reset_cmd))
    application.add_handler(CommandHandler("resetall", resetall_cmd))
    application.add_handler(CommandHandler("givebonus", givebonus_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("funnel", funnel_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    
    # Callbacks (botões)
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Mensagens
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
            message_handler
        )
    )
    
    logger.info("✅ Todos handlers registrados (v7.2)")
    return application

# ═══════════════════════════════════════════════════════════════════════════════
# 🌐 FLASK APP (Webhook)
# ═══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
application = setup_application()

# Event loop para asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def start_loop():
    """Inicia event loop em thread separada"""
    loop.run_forever()

import threading
threading.Thread(target=start_loop, daemon=True).start()

@app.route("/", methods=["GET"])
def health():
    """Health check"""
    return "ok", 200

@app.route("/set-webhook", methods=["GET"])
def set_webhook_route():
    """Endpoint para configurar webhook manualmente"""
    asyncio.run_coroutine_threadsafe(setup_webhook(), loop)
    return "Webhook configurado", 200

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    """Recebe updates do Telegram"""
    try:
        data = request.json
        if not data:
            return "ok", 200
        
        update = Update.de_json(data, application.bot)
        asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            loop
        )
        return "ok", 200
        
    except Exception as e:
        logger.exception(f"Erro webhook: {e}")
        return "error", 500

async def setup_webhook():
    """Configura webhook no Telegram"""
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook configurado: {webhook_url}")
        
        # Inicia scheduler de engagement
        asyncio.create_task(engagement_scheduler(application.bot))
        
    except Exception as e:
        logger.error(f"Erro configurando webhook: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# 🎬 MAIN - Ponto de entrada
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Inicializa aplicação
    asyncio.run_coroutine_threadsafe(application.initialize(), loop)
    asyncio.run_coroutine_threadsafe(application.start(), loop)
    asyncio.run_coroutine_threadsafe(engagement_scheduler(application.bot), loop)
    
    # Inicia Flask
    logger.info(f"🌐 Servidor Flask rodando na porta {PORT}")
    logger.info("🚀 Sophia Bot v7.2 CLEAN totalmente operacional!")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
