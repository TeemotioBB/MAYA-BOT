#!/usr/bin/env python3
"""
🔥 WEBHOOK PUSHINPAY - SISTEMA SIMPLIFICADO
Usa seus links de checkout atuais + webhook para ativação automática
"""
import logging
import redis
from datetime import datetime, timedelta
from flask import request, jsonify

# ================= CONFIGURAÇÃO =================
logger = logging.getLogger(__name__)

REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"
DIAS_VIP = 7

# ⚠️ NÃO PRECISA DE TOKEN! Este código só RECEBE webhooks, não faz chamadas à API

# ================= REDIS =================
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()
    logger.info("✅ Redis conectado (webhook)")
except Exception as e:
    logger.error(f"❌ Redis erro: {e}")
    raise

# ================= REDIS KEYS =================
def vip_key(uid): 
    return f"vip:{uid}"

def awaiting_payment_key(uid):
    """Marca que usuário está aguardando pagamento"""
    return f"awaiting_payment:{uid}"

def recent_payment_key(transaction_id):
    """Armazena pagamento recente para identificação"""
    return f"recent_payment:{transaction_id}"

def all_users_key():
    return "all_users"

# ================= FUNÇÕES AUXILIARES =================
def get_all_active_users():
    try:
        users = r.smembers(all_users_key())
        return [int(uid) for uid in users]
    except:
        return []

def is_awaiting_payment(uid):
    """Verifica se usuário clicou recentemente em link de pagamento"""
    try:
        return r.exists(awaiting_payment_key(uid))
    except:
        return False

def mark_awaiting_payment(uid):
    """Marca que usuário clicou no link de pagamento"""
    try:
        timestamp = datetime.now().isoformat()
        # Expira em 2 horas
        r.setex(awaiting_payment_key(uid), timedelta(hours=2), timestamp)
        logger.info(f"💳 User {uid} aguardando pagamento")
    except:
        pass

def clear_awaiting_payment(uid):
    """Remove flag de aguardando pagamento"""
    try:
        r.delete(awaiting_payment_key(uid))
    except:
        pass

# ================= ATIVAR VIP =================
async def ativar_vip(uid: int, transaction_id: str, valor: float, bot):
    """
    Ativa VIP para o usuário
    """
    try:
        logger.info(f"💎 Ativando VIP para {uid} - Transação: {transaction_id}")
        
        # Ativa VIP
        vip_until = datetime.now() + timedelta(days=DIAS_VIP)
        r.set(vip_key(uid), vip_until.isoformat())
        
        # Remove flag de aguardando
        clear_awaiting_payment(uid)
        
        # Mensagem de sucesso
        mensagem = (
            "💖 **PAGAMENTO CONFIRMADO!** 💖\n\n"
            f"💰 Valor: R$ {valor:.2f}\n"
            f"👑 VIP ativado por **{DIAS_VIP} dias**\n"
            f"📅 Válido até: **{vip_until.strftime('%d/%m/%Y')}**\n\n"
            "✅ **Você desbloqueou:**\n"
            "🔓 Conversas ilimitadas\n"
            "📸 Fotos exclusivas VIP\n"
            "🔥 Respostas mais ousadas\n"
            "⚡ Prioridade total\n\n"
            "Agora me conta... o que você quer fazer comigo? 😏💕"
        )
        
        await bot.send_message(uid, mensagem, parse_mode="Markdown")
        
        # Envia fotos VIP
        try:
            from main import send_vip_welcome_photos
            await send_vip_welcome_photos(bot, uid)
        except:
            logger.warning("⚠️ Não foi possível enviar fotos VIP")
        
        # Notifica admin
        try:
            from main import ADMIN_IDS
            for admin_id in ADMIN_IDS:
                await bot.send_message(
                    admin_id,
                    f"💎 **NOVO VIP AUTOMÁTICO!**\n\n"
                    f"👤 User: `{uid}`\n"
                    f"💰 Valor: R$ {valor:.2f}\n"
                    f"🎫 Transaction: `{transaction_id}`\n"
                    f"📅 Válido até: {vip_until.strftime('%d/%m/%Y')}",
                    parse_mode="Markdown"
                )
        except:
            pass
        
        logger.info(f"✅ VIP ativado: {uid}")
        return True
        
    except Exception as e:
        logger.exception(f"❌ Erro ao ativar VIP: {e}")
        return False

# ================= IDENTIFICAR USUÁRIO =================
def identificar_usuario_por_valor_e_tempo(valor: float):
    """
    Identifica usuário baseado no valor pago e timestamp
    Procura quem clicou no link recentemente
    """
    try:
        # Lista todos usuários ativos
        users = get_all_active_users()
        
        # Filtra quem está aguardando pagamento
        candidatos = []
        for uid in users:
            if is_awaiting_payment(uid):
                # Pega timestamp de quando clicou
                timestamp_str = r.get(awaiting_payment_key(uid))
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    # Se clicou há menos de 2 horas
                    if (datetime.now() - timestamp).total_seconds() < 7200:
                        candidatos.append((uid, timestamp))
        
        if not candidatos:
            logger.warning(f"⚠️ Nenhum usuário aguardando pagamento de R$ {valor:.2f}")
            return None
        
        # Ordena por mais recente
        candidatos.sort(key=lambda x: x[1], reverse=True)
        
        # Se só tem 1, é esse
        if len(candidatos) == 1:
            logger.info(f"✅ Identificado: {candidatos[0][0]} (único aguardando)")
            return candidatos[0][0]
        
        # Se tem múltiplos, pega o mais recente
        # (assumindo que é improvável 2 pagarem no mesmo minuto)
        logger.info(f"✅ Identificado: {candidatos[0][0]} (mais recente)")
        return candidatos[0][0]
        
    except Exception as e:
        logger.exception(f"❌ Erro ao identificar usuário: {e}")
        return None

# ================= WEBHOOK HANDLER =================
async def processar_webhook_pushinpay(payload: dict, bot):
    """
    Processa webhook da PushinPay
    
    Payload esperado:
    {
        "id": "uuid",
        "status": "paid" | "created" | "expired",
        "value": 999,  // em centavos
        ...
    }
    """
    try:
        logger.info(f"📥 Webhook PushinPay: {payload}")
        
        transaction_id = payload.get("id")
        status = payload.get("status")
        value_centavos = payload.get("value", 0)
        
        # Converte centavos para reais
        try:
            value_reais = float(value_centavos) / 100
        except:
            value_reais = 0.0
        
        if not transaction_id:
            logger.error("❌ Webhook sem ID")
            return False
        
        # Ignora se não for pagamento aprovado
        if status != "paid":
            logger.info(f"ℹ️ Status '{status}' ignorado para {transaction_id}")
            return False
        
        # Verifica se já processamos este pagamento
        if r.exists(recent_payment_key(transaction_id)):
            logger.info(f"⚠️ Pagamento {transaction_id} já processado")
            return False
        
        # Marca como processado (expira em 7 dias)
        r.setex(recent_payment_key(transaction_id), timedelta(days=7), "processed")
        
        # Tenta identificar usuário
        uid = identificar_usuario_por_valor_e_tempo(value_reais)
        
        if uid:
            # IDENTIFICADO! Ativa automaticamente
            logger.info(f"🎯 Pagamento identificado: {transaction_id} → User {uid}")
            await ativar_vip(uid, transaction_id, value_reais, bot)
            return True
        else:
            # NÃO IDENTIFICADO - Envia para admin aprovar
            logger.warning(f"❓ Pagamento não identificado: {transaction_id}")
            
            try:
                from main import ADMIN_IDS
                
                mensagem_admin = (
                    "⚠️ **PAGAMENTO NÃO IDENTIFICADO**\n\n"
                    f"💰 Valor: R$ {value_reais:.2f}\n"
                    f"🎫 Transaction ID:\n`{transaction_id}`\n\n"
                    "**Nenhum usuário encontrado aguardando pagamento deste valor.**\n\n"
                    "Use `/setvip <user_id>` para ativar manualmente."
                )
                
                for admin_id in ADMIN_IDS:
                    await bot.send_message(admin_id, mensagem_admin, parse_mode="Markdown")
            except:
                pass
            
            return False
        
    except Exception as e:
        logger.exception(f"❌ Erro ao processar webhook: {e}")
        return False

# ================= ADICIONAR AO FLASK =================
def adicionar_rota_webhook(app, application, loop):
    """
    Adiciona rota de webhook ao Flask
    
    Uso:
        from webhook_pushinpay import adicionar_rota_webhook
        adicionar_rota_webhook(app, application, loop)
    """
    import asyncio
    
    @app.route("/webhook/pushinpay", methods=["POST"])
    def webhook_pushinpay():
        """Endpoint que recebe webhooks da PushinPay"""
        try:
            data = request.json
            if not data:
                logger.warning("❌ Webhook sem dados")
                return jsonify({"error": "No data"}), 400
            
            logger.info(f"📨 Webhook recebido: ID={data.get('id')}, Status={data.get('status')}")
            
            # Processa de forma assíncrona
            asyncio.run_coroutine_threadsafe(
                processar_webhook_pushinpay(data, application.bot),
                loop
            )
            
            # Retorna 200 imediatamente
            return jsonify({"status": "received"}), 200
            
        except Exception as e:
            logger.exception(f"❌ Erro no webhook: {e}")
            return jsonify({"status": "error"}), 200
    
    logger.info("✅ Rota /webhook/pushinpay registrada")
