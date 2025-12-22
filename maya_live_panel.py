import sqlite3
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Any
import os

DB = "maya.db"
app = FastAPI(title="Maya Live Panel")

# Simple templates/static setup (the file serves a self-contained HTML below as fallback)
BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
if not os.path.exists(TEMPLATES_DIR):
    os.makedirs(TEMPLATES_DIR, exist_ok=True)

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# -------------------- Database helpers --------------------
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, name, is_vip, msg_count, vip_until FROM users ORDER BY msg_count DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_messages_for_user(user_id: int, since_id: int = 0, limit: int = 500):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, direction, text, created_at FROM messages WHERE user_id=? AND id>? ORDER BY id ASC LIMIT ?",
        (user_id, since_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_last_message_id():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT MAX(id) as last FROM messages")
    r = cur.fetchone()
    conn.close()
    return r[0] or 0

# -------------------- WebSocket manager --------------------
class ConnectionManager:
    def __init__(self):
        # Keep global watchers and per-user watchers
        self.global_connections: List[WebSocket] = []
        self.user_connections: Dict[int, List[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        async with self.lock:
            self.global_connections.append(websocket)

    async def connect_user(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        async with self.lock:
            self.user_connections.setdefault(user_id, []).append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self.lock:
            if websocket in self.global_connections:
                self.global_connections.remove(websocket)
            for k, v in list(self.user_connections.items()):
                if websocket in v:
                    v.remove(websocket)
                    if not v:
                        del self.user_connections[k]

    async def broadcast_global(self, message: dict):
        # send to all global watchers
        async with self.lock:
            websockets = list(self.global_connections)
        for ws in websockets:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(ws)

    async def broadcast_user(self, user_id: int, message: dict):
        async with self.lock:
            conns = list(self.user_connections.get(user_id, []))
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(ws)

manager = ConnectionManager()

# -------------------- REST endpoints --------------------
@app.get("/api/users")
async def api_users():
    return JSONResponse(get_users())

@app.get("/api/messages/{user_id}")
async def api_messages(user_id: int, since: int = 0):
    return JSONResponse(get_messages_for_user(user_id, since_id=since))

@app.post("/api/mark_vip/{user_id}")
async def api_mark_vip(user_id: int, days: int = 30):
    # mark user vip in DB
    conn = get_conn()
    cur = conn.cursor()
    from datetime import datetime, timedelta
    until = (datetime.now() + timedelta(days=days)).isoformat()
    cur.execute("UPDATE users SET is_vip=1, vip_until=? WHERE user_id=?", (until, user_id))
    conn.commit()
    conn.close()
    # notify watchers
    await manager.broadcast_global({"type": "vip_update", "user_id": user_id, "vip_until": until})
    return JSONResponse({"ok": True})

@app.post("/api/send_bot_message/{user_id}")
async def api_send_bot_message(user_id: int, request: Request):
    data = await request.json()
    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (user_id, direction, text) VALUES (?,?,?)", (user_id, "bot", text))
    conn.commit()
    msg_id = cur.lastrowid
    cur.execute("SELECT id, user_id, direction, text, created_at FROM messages WHERE id=?", (msg_id,))
    row = cur.fetchone()
    conn.close()
    msg = dict(row)
    # broadcast to global and per-user viewers
    await manager.broadcast_global({"type": "message", "message": msg})
    await manager.broadcast_user(user_id, {"type": "message", "message": msg})
    return JSONResponse(msg)

# -------------------- HTML (single-file app) --------------------
SINGLE_HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Maya Live Panel</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#0b1220;--card:#0f1724;--muted:#9aa4b2;--accent:#f97316}
body{margin:0;font-family:Inter,Segoe UI,Arial;background:var(--bg);color:#e6eef6}
.header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#061029}
.container{display:flex;height:calc(100vh - 52px)}
.sidebar{width:320px;border-right:1px solid rgba(255,255,255,0.04);padding:12px;overflow:auto}
.main{flex:1;padding:12px;display:flex;flex-direction:column}
.user-item{padding:8px;border-radius:8px;margin-bottom:8px;background:rgba(255,255,255,0.02);cursor:pointer}
.user-item:hover{background:rgba(255,255,255,0.03)}
.user-item .meta{display:flex;justify-content:space-between}
.messages{flex:1;overflow:auto;padding:8px;border-radius:8px;background:rgba(255,255,255,0.01)}
.msg{margin-bottom:8px;padding:8px;border-radius:8px}
.msg.user{background:rgba(34,197,94,0.08)}
.msg.bot{background:rgba(236,72,153,0.06)}
.controls{display:flex;gap:8px;margin-top:8px}
input[type=text]{flex:1;padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.06);background:transparent;color:inherit}
button{padding:10px 12px;border-radius:8px;border:0;background:var(--accent);color:#fff;cursor:pointer}
.small{font-size:12px;color:var(--muted)}
.vip-tag{color:var(--accent);font-weight:700;margin-left:6px}
</style>
</head>
<body>
<div class="header"><div><strong>Maya Live Panel</strong> <span class="small">(real-time per user)</span></div><div id="status" class="small">desconectado</div></div>
<div class="container">
  <div class="sidebar">
    <div style="margin-bottom:8px"><input id="search" placeholder="buscar por id ou nome" style="width:100%;padding:8px;border-radius:6px;background:transparent;border:1px solid rgba(255,255,255,0.04);color:inherit"></div>
    <div id="users"></div>
  </div>
  <div class="main">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
      <div><strong id="selected_title">Selecione um usuário</strong><span id="selected_vip" class="vip-tag"></span></div>
      <div style="margin-left:auto"><button id="refresh_users">Atualizar</button></div>
    </div>
    <div class="messages" id="messages"></div>
    <div style="display:flex;align-items:center;gap:8px;margin-top:8px">
      <input type="text" id="msg_input" placeholder="Enviar mensagem como BOT (apenas para admin)">
      <button id="send_btn">Enviar</button>
      <button id="mark_vip" style="background:#0ea5a4">Marcar VIP</button>
    </div>
    <div class="small" style="margin-top:6px">Conexão websocket: <span id="ws_state">desconectado</span></div>
  </div>
</div>
<script>
let users = [];
let selectedUser = null;
let wsGlobal = null;
let wsUser = null;
let lastMsgId = 0;

function el(q){return document.querySelector(q)}

async function fetchUsers(){
  const res = await fetch('/api/users');
  users = await res.json();
  renderUserList();
}

function renderUserList(){
  const box = el('#users'); box.innerHTML='';
  const search = el('#search').value.trim().toLowerCase();
  users.forEach(u=>{
    if(search){
      if(!(String(u.user_id).includes(search) || (u.name||'').toLowerCase().includes(search))) return;
    }
    const div = document.createElement('div'); div.className='user-item';
    div.innerHTML = `<div class="meta"><div><strong>${u.name||'sem_nome'}</strong> <span class="small">[${u.user_id}]</span> ${u.is_vip?'<span class="vip-tag">VIP</span>':''}</div><div class="small">msgs:${u.msg_count||0}</div></div>`;
    div.onclick = ()=>selectUser(u);
    box.appendChild(div);
  });
}

function selectUser(u){
  selectedUser = u; lastMsgId = 0; el('#selected_title').textContent = (u.name||'sem_nome') + ' ['+u.user_id+']';
  el('#selected_vip').textContent = u.is_vip?('VIP até '+(u.vip_until||'')) : '';
  el('#messages').innerHTML='';
  connectUserWS(u.user_id);
  loadMessages(u.user_id);
}

async function loadMessages(user_id){
  const res = await fetch(`/api/messages/${user_id}?since=0`);
  const msgs = await res.json();
  const box = el('#messages');
  msgs.forEach(m=>{
    appendMessage(m);
    lastMsgId = Math.max(lastMsgId, m.id);
  });
}

function appendMessage(m){
  const box = el('#messages');
  const d = document.createElement('div'); d.className='msg '+(m.direction==='user'?'user':'bot');
  d.innerHTML = `<div class="small">[${m.id}] ${m.created_at || ''}</div><div>${escapeHtml(m.text||'')}</div>`;
  box.appendChild(d); box.scrollTop = box.scrollHeight;
}

function escapeHtml(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// Global websocket to receive all events (new messages / vip updates)
function connectGlobalWS(){
  if(wsGlobal) wsGlobal.close();
  wsGlobal = new WebSocket('ws://'+window.location.host+'/ws');
  wsGlobal.onopen = ()=>{ el('#status').textContent='conectado'; el('#ws_state').textContent='global conectado'; };
  wsGlobal.onclose = ()=>{ el('#status').textContent='desconectado'; el('#ws_state').textContent='global desconectado'; setTimeout(connectGlobalWS,2000); };
  wsGlobal.onerror = ()=>{ el('#status').textContent='erro'; };
  wsGlobal.onmessage = (ev)=>{
    const data = JSON.parse(ev.data);
    if(Array.isArray(data)){
      // initial bulk messages
      data.forEach(m=>{});
    } else if(data.type==='message'){
      // new message global; update user list and if opened user append
      const m = data.message;
      refreshUserInList(m.user_id);
      if(selectedUser && selectedUser.user_id===m.user_id){ appendMessage(m); lastMsgId = Math.max(lastMsgId,m.id); }
    } else if(data.type==='vip_update'){
      refreshUserInList(data.user_id);
    }
  };
}

function refreshUserInList(user_id){
  fetchUsers();
}

// Per-user WS (for focused view) - optional, server also sends per-user broadcasts to /ws endpoint
function connectUserWS(user_id){
  if(wsUser) wsUser.close();
  wsUser = new WebSocket('ws://'+window.location.host+`/ws/user/${user_id}`);
  wsUser.onopen = ()=>{ el('#ws_state').textContent='user connected'; };
  wsUser.onclose = ()=>{ el('#ws_state').textContent='user disconnected'; };
  wsUser.onmessage = (ev)=>{
    const data = JSON.parse(ev.data);
    if(data.type==='message') appendMessage(data.message);
    if(data.type==='vip_update') el('#selected_vip').textContent = 'VIP até '+(data.vip_until||'');
  };
}

// controls
el('#refresh_users').onclick = ()=>fetchUsers();
el('#search').addEventListener('input', ()=>renderUserList());
el('#send_btn').onclick = async ()=>{
  if(!selectedUser) return alert('Selecione um usuário');
  const text = el('#msg_input').value.trim(); if(!text) return;
  await fetch(`/api/send_bot_message/${selectedUser.user_id}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  el('#msg_input').value='';
};
el('#mark_vip').onclick = async ()=>{
  if(!selectedUser) return alert('Selecione um usuário');
  await fetch(`/api/mark_vip/${selectedUser.user_id}`, {method:'POST'});
  alert('Usuário marcado como VIP');
  fetchUsers();
};

// start
fetchUsers(); connectGlobalWS();
</script>
</body>
</html>
"""

@app.get("/live")
async def live_panel():
    return HTMLResponse(SINGLE_HTML)

# -------------------- WebSocket endpoints --------------------
@app.websocket("/ws")
async def websocket_global(ws: WebSocket):
    await manager.connect_global(ws)
    try:
        # send last 100 messages on connect
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, direction, text, created_at FROM messages ORDER BY id DESC LIMIT 100")
        rows = cur.fetchall()
        conn.close()
        recent = [dict(r) for r in reversed(rows)]
        if recent:
            await ws.send_json(recent)
        while True:
            await asyncio.sleep(0.8)
            # keepalive
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)

@app.websocket("/ws/user/{user_id}")
async def websocket_user(ws: WebSocket, user_id: int):
    await manager.connect_user(ws, user_id)
    try:
        # on connect, send last 200 messages of that user
        rows = get_messages_for_user(user_id, since_id=0, limit=200)
        if rows:
            await ws.send_json(rows)
        while True:
            await asyncio.sleep(0.8)
            # keepalive - nothing else needed; server will push via manager.broadcast_user
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)

# -------------------- Helpers to notify manager when new messages inserted by other processes --------------------
# If your main bot process writes to the same DB, this panel will pick up new messages via polling on websocket connections
# Additionally, we expose a lightweight notifier endpoint that the bot can call when it inserts a message to push instantly

@app.post('/notify_new_message')
async def notify_new_message(payload: Dict[str, Any]):
    """Optional: call this from your bot right after inserting a message. Payload should include: message_id"""
    mid = payload.get('message_id')
    if not mid:
        raise HTTPException(status_code=400, detail='message_id required')
    conn = get_conn(); cur = conn.cursor(); cur.execute('SELECT id, user_id, direction, text, created_at FROM messages WHERE id=?', (mid,)); row = cur.fetchone(); conn.close()
    if not row:
        raise HTTPException(status_code=404, detail='message not found')
    msg = dict(row)
    await manager.broadcast_global({"type": "message", "message": msg})
    await manager.broadcast_user(msg['user_id'], {"type": "message", "message": msg})
    return JSONResponse({"ok": True})

# -------------------- Run note --------------------
# Run with: uvicorn maya_live_panel:app --host 0.0.0.0 --port 8000 --reload
# Optional: call /notify_new_message from your bot after inserting a new message to push instantly to connected panels
