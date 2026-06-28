import asyncio
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import uvicorn

tcp_sessions = {}
admin_connections = set()

def init_db():
    conn = sqlite3.connect("shellhub.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, remote_addr TEXT, name TEXT DEFAULT '',
        notes TEXT DEFAULT '', flags TEXT DEFAULT '',
        created_at REAL, last_seen REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT, type TEXT, data TEXT, timestamp REAL
    )""")
    conn.commit()
    conn.close()

def save_session(sid, addr, created):
    conn = sqlite3.connect("shellhub.db")
    conn.execute("INSERT OR REPLACE INTO sessions (id, remote_addr, created_at, last_seen) VALUES (?, ?, ?, ?)",
                 (sid, addr, created, time.time()))
    conn.commit()
    conn.close()

def get_session_meta(sid):
    conn = sqlite3.connect("shellhub.db")
    c = conn.cursor()
    c.execute("SELECT name, notes, flags FROM sessions WHERE id = ?", (sid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"name": row[0] or "", "notes": row[1] or "", "flags": row[2] or ""}
    return {"name": "", "notes": "", "flags": ""}

def update_session_meta(sid, field, value):
    conn = sqlite3.connect("shellhub.db")
    conn.execute(f"UPDATE sessions SET {field} = ?, last_seen = ? WHERE id = ?", (value, time.time(), sid))
    conn.commit()
    conn.close()

def save_command(sid, typ, data):
    conn = sqlite3.connect("shellhub.db")
    conn.execute("INSERT INTO commands (session_id, type, data, timestamp) VALUES (?, ?, ?, ?)",
                 (sid, typ, data, time.time()))
    conn.commit()
    conn.close()

def get_history(sid):
    conn = sqlite3.connect("shellhub.db")
    c = conn.cursor()
    c.execute("SELECT type, data FROM commands WHERE session_id = ? ORDER BY id", (sid,))
    rows = c.fetchall()
    conn.close()
    return rows

async def broadcast_sessions():
    slist = []
    for s in tcp_sessions.values():
        meta = get_session_meta(s["id"])
        slist.append({
            "id": s["id"], "addr": s["addr"],
            "name": meta["name"], "notes": meta["notes"], "flags": meta["flags"],
            "created": s["created"], "active": True
        })
    dead = []
    for ws in admin_connections:
        try:
            await ws.send_json({"type": "sessions", "list": slist})
        except:
            dead.append(ws)
    for ws in dead:
        admin_connections.discard(ws)

async def handle_tcp(reader, writer):
    sid = uuid.uuid4().hex[:8]
    addr = writer.get_extra_info("peername")
    addr_str = f"{addr[0]}:{addr[1]}"
    created = time.time()

    session = {"id": sid, "addr": addr_str, "reader": reader,
               "writer": writer, "created": created, "buf": b""}
    tcp_sessions[sid] = session
    save_session(sid, addr_str, created)
    await broadcast_sessions()

    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            session["buf"] += data
            text = data.decode("utf-8", errors="replace")
            save_command(sid, "output", text)
            for ws in admin_connections:
                if getattr(ws, "watching", None) == sid:
                    try:
                        await ws.send_json({"type": "output", "session_id": sid, "data": text})
                    except:
                        pass
    except:
        pass
    finally:
        writer.close()
        await writer.wait_closed()
        tcp_sessions.pop(sid, None)
        await broadcast_sessions()

@asynccontextmanager
async def lifespan(app):
    init_db()
    server = await asyncio.start_server(handle_tcp, "0.0.0.0", 4444)
    task = asyncio.create_task(server.serve_forever())
    yield
    task.cancel()
    server.close()

app = FastAPI(lifespan=lifespan)

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ws.watching = None
    admin_connections.add(ws)

    slist = []
    for s in tcp_sessions.values():
        meta = get_session_meta(s["id"])
        slist.append({
            "id": s["id"], "addr": s["addr"],
            "name": meta["name"], "notes": meta["notes"], "flags": meta["flags"],
            "created": s["created"], "active": True
        })
    await ws.send_json({"type": "sessions", "list": slist})

    try:
        while True:
            msg = await ws.receive_json()
            if msg["type"] == "watch":
                ws.watching = msg["session_id"]
                history = get_history(msg["session_id"])
                meta = get_session_meta(msg["session_id"])
                await ws.send_json({"type": "meta", "session_id": msg["session_id"], **meta})
                for typ, data in history:
                    await ws.send_json({"type": typ, "session_id": msg["session_id"], "data": data})
            elif msg["type"] == "rename":
                update_session_meta(msg["session_id"], "name", msg["data"])
                await broadcast_sessions()
            elif msg["type"] == "notes":
                update_session_meta(msg["session_id"], "notes", msg["data"])
            elif msg["type"] == "flag":
                update_session_meta(msg["session_id"], "flags", msg["data"])
            elif msg["type"] == "input":
                s = tcp_sessions.get(msg["session_id"])
                if s:
                    data = msg["data"].replace("\r", "\n")
                    s["writer"].write(data.encode())
                    await s["writer"].drain()
    except WebSocketDisconnect:
        pass
    finally:
        admin_connections.discard(ws)

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.get("/cheatsheet")
async def cheatsheet():
    return FileResponse("static/cheatsheet.html")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
