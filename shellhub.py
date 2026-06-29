import asyncio
import logging
import os
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("shellhub")

tcp_sessions = {}
admin_connections = set()
tcp_tasks = set()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shellhub.db")
CFG_HOST = os.environ.get("SHELLHUB_HOST", "0.0.0.0")
CFG_PORT = int(os.environ.get("SHELLHUB_PORT", "8080"))
CFG_TCP_HOST = os.environ.get("SHELLHUB_TCP_HOST", "0.0.0.0")
CFG_TCP_PORT = int(os.environ.get("SHELLHUB_TCP_PORT", "4444"))
CFG_TOKEN = os.environ.get("SHELLHUB_TOKEN", "")

CONTROL_RE = re.compile(r"[\x00\x07\x0b\x0c\x0e-\x1a\x1c-\x1f\x7f]")

def clean_output(text):
    text = text.replace("\r\n", "\n")
    text = CONTROL_RE.sub("", text)
    return text

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, remote_addr TEXT, name TEXT DEFAULT '',
            notes TEXT DEFAULT '', flags TEXT DEFAULT '',
            created_at REAL, last_seen REAL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, type TEXT, data TEXT, timestamp REAL
        )""")

def save_session(sid, addr, created):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO sessions (id, remote_addr, created_at, last_seen) VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen",
                     (sid, addr, created, time.time()))

def get_session_meta(sid):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT name, notes, flags FROM sessions WHERE id = ?", (sid,)).fetchone()
    if row:
        return {"name": row[0] or "", "notes": row[1] or "", "flags": row[2] or ""}
    return {"name": "", "notes": "", "flags": ""}

META_COLUMNS = {
    "name": "name",
    "notes": "notes",
    "flags": "flags",
}

META_MAXLEN = {"name": 100, "notes": 2000, "flags": 500}

def update_session_meta(sid, field, value):
    column = META_COLUMNS.get(field)
    if column is None:
        return
    maxlen = META_MAXLEN.get(field, 500)
    if isinstance(value, str):
        value = value[:maxlen]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE sessions SET {column} = ?, last_seen = ? WHERE id = ?", (value, time.time(), sid))

def save_command(sid, typ, data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO commands (session_id, type, data, timestamp) VALUES (?, ?, ?, ?)",
                     (sid, typ, data, time.time()))

def get_history(sid):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT type, data FROM commands WHERE session_id = ? ORDER BY id LIMIT 50000", (sid,)).fetchall()
    return rows

async def broadcast_sessions():
    slist = []
    for s in list(tcp_sessions.values()):
        meta = get_session_meta(s["id"])
        slist.append({
            "id": s["id"], "addr": s["addr"],
            "name": meta["name"], "notes": meta["notes"], "flags": meta["flags"],
            "created": s["created"], "active": True
        })
    dead = []
    for ws in list(admin_connections):
        try:
            await ws.send_json({"type": "sessions", "list": slist})
        except Exception:
            dead.append(ws)
    for ws in dead:
        admin_connections.discard(ws)

async def handle_tcp(reader, writer):
    task = asyncio.current_task()
    tcp_tasks.add(task)
    sid = uuid.uuid4().hex[:8]
    addr = writer.get_extra_info("peername")
    addr_str = f"{addr[0]}:{addr[1]}"
    created = time.time()

    session = {"id": sid, "addr": addr_str, "reader": reader,
               "writer": writer, "created": created, "raw_mode": False, "output_raw": False}
    tcp_sessions[sid] = session
    save_session(sid, addr_str, created)
    await broadcast_sessions()

    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            raw = data.decode("utf-8", errors="replace")
            if session.get("output_raw"):
                text = raw
            else:
                text = clean_output(raw)
            save_command(sid, "output", raw)
            dead = []
            for ws in list(admin_connections):
                if getattr(ws, "watching", None) == sid:
                    try:
                        await ws.send_json({"type": "output", "session_id": sid, "data": text})
                    except Exception as e:
                        dead.append(ws)
                        log.debug("ws send failed: %s", e)
            for ws in dead:
                admin_connections.discard(ws)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.error("handle_tcp error (session %s): %s", sid, e)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        tcp_sessions.pop(sid, None)
        await broadcast_sessions()
        tcp_tasks.discard(task)

@asynccontextmanager
async def lifespan(app):
    init_db()
    server = await asyncio.start_server(handle_tcp, CFG_TCP_HOST, CFG_TCP_PORT)
    serve_task = asyncio.create_task(server.serve_forever())
    yield
    serve_task.cancel()
    for t in list(tcp_tasks):
        t.cancel()
    if tcp_tasks:
        await asyncio.gather(*tcp_tasks, return_exceptions=True)
    server.close()
    await server.wait_closed()

app = FastAPI(lifespan=lifespan)

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if CFG_TOKEN:
        token = ws.query_params.get("token", "")
        if token != CFG_TOKEN:
            await ws.close(code=4001, reason="unauthorized")
            return
    await ws.accept()
    ws.watching = None
    admin_connections.add(ws)

    slist = []
    for s in list(tcp_sessions.values()):
        meta = get_session_meta(s["id"])
        slist.append({
            "id": s["id"], "addr": s["addr"],
            "name": meta["name"], "notes": meta["notes"], "flags": meta["flags"],
            "created": s["created"], "active": True
        })
    await ws.send_json({"type": "sessions", "list": slist})

    try:
        while True:
            raw = await ws.receive_json()
            msg = raw if isinstance(raw, dict) else {}
            t = msg.get("type")

            if t == "watch":
                sid = msg.get("session_id")
                ws.watching = sid
                if sid:
                    meta = get_session_meta(sid)
                    await ws.send_json({"type": "meta", "session_id": sid, **meta})
                    for typ, data in get_history(sid):
                        cleaned = clean_output(data) if typ == "output" else data
                        await ws.send_json({"type": "history_line", "session_id": sid, "data_type": typ, "data": cleaned})
            elif t == "rename":
                update_session_meta(msg.get("session_id"), "name", msg.get("data", ""))
                await broadcast_sessions()
            elif t == "notes":
                update_session_meta(msg.get("session_id"), "notes", msg.get("data", ""))
                await broadcast_sessions()
            elif t == "flag":
                update_session_meta(msg.get("session_id"), "flags", msg.get("data", ""))
                await broadcast_sessions()
            elif t == "raw_mode":
                s = tcp_sessions.get(msg.get("session_id"))
                if s:
                    val = msg.get("data", False)
                    s["raw_mode"] = val
                    s["output_raw"] = val
            elif t == "pty_spawn":
                s = tcp_sessions.get(msg.get("session_id"))
                if s:
                    payload = msg.get("payload", "python3 -c 'import pty;pty.spawn(\"/bin/bash\")'")
                    data = payload + "\n"
                    s["writer"].write(data.encode())
                    await s["writer"].drain()
            elif t == "input":
                s = tcp_sessions.get(msg.get("session_id"))
                if s:
                    data = msg.get("data", "")
                    if not s["raw_mode"]:
                        data = data.replace("\r", "\n")
                    s["writer"].write(data.encode())
                    await s["writer"].drain()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        log.error("ws_endpoint error: %s", e)
    finally:
        admin_connections.discard(ws)

@app.get("/")
async def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

@app.get("/cheatsheet")
async def cheatsheet():
    return FileResponse(os.path.join(BASE_DIR, "static", "cheatsheet.html"))

if __name__ == "__main__":
    uvicorn.run(app, host=CFG_HOST, port=CFG_PORT)
