import os
import time
import uuid
import threading
import re
from collections import deque
from typing import Dict, Deque, Any

from flask import Flask, request, jsonify, Response

# Safe fallback HTML (no template dependency)
PAIR_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pair TikTok Live to Roblox</title>
<style>
body{font-family:Arial,sans-serif;background:#070b16;color:#fff;display:flex;justify-content:center;padding:40px}
.card{width:min(92vw,520px);background:#0f1629;border:1px solid #27314d;border-radius:18px;padding:24px}
h1{margin:0 0 18px;font-size:22px}
label{display:block;margin:14px 0 6px;font-weight:700}
input{width:100%;padding:14px;border-radius:12px;border:1px solid #2c395e;background:#091025;color:#fff}
button{width:100%;padding:14px;border:0;border-radius:12px;background:#6d5efc;color:#fff;font-weight:700;margin-top:18px;cursor:pointer}
.note{margin-top:18px;color:#cfe0ff;background:#0b1733;padding:14px;border-radius:12px}
.ok{background:#0f4023;color:#d9ffe6;padding:12px;border-radius:12px;margin-top:14px}
.err{background:#4a1a1a;color:#ffdede;padding:12px;border-radius:12px;margin-top:14px}
small{opacity:.75}
</style>
</head>
<body>
  <div class="card">
    <h1>Pair TikTok Live to Roblox</h1>
    <div>Enter the room code shown inside the Roblox game, then enter the TikTok live username to connect this room to that live.</div>
    {message_block}
    <form method="post" action="/pair">
      <label>Room code</label>
      <input name="room" value="{room}" placeholder="1234">
      <label>TikTok username</label>
      <input name="username" value="{username}" placeholder="sp200921">
      <button type="submit">Pair now</button>
    </form>
    <div class="note">
      <div><strong>How to use:</strong></div>
      <ol>
        <li>Open the game and enter a room code.</li>
        <li>Open this page on your phone.</li>
        <li>Pair the same room code to your TikTok username.</li>
        <li>Back in Roblox, press <code>Connect</code>.</li>
      </ol>
      <small>This debug build prints verbose logs in Render so we can see comments, likes, gifts, and follows.</small>
    </div>
  </div>
</body>
</html>
"""

SHARED_SECRET = os.getenv("SHARED_SECRET", "")
PORT = int(os.getenv("PORT", "10000"))

app = Flask(__name__)

# In-memory state
pairings: Dict[str, Dict[str, Any]] = {}      # roomCode -> {username, pairedAt}
sessions: Dict[str, Dict[str, Any]] = {}      # sessionKey -> {roomCode, streamerId, queue, createdAt}
listeners: Dict[str, Dict[str, Any]] = {}     # streamerId -> {thread, active, startedAt, error}
lock = threading.RLock()

def log(msg: str):
    print(f"[DEBUG] {time.strftime('%H:%M:%S')} {msg}", flush=True)

def normalize_room(value: str) -> str:
    value = str(value or "").strip().upper()
    value = re.sub(r"[^A-Z0-9_-]", "", value)
    return value[:32]

def normalize_username(value: str) -> str:
    value = str(value or "").strip()
    value = value.lstrip("@")
    return value

def broadcast(streamer_id: str, event: Dict[str, Any]):
    with lock:
        delivered = 0
        for session in sessions.values():
            if session.get("streamerId") == streamer_id:
                q: Deque[dict] = session["queue"]
                q.append(event)
                delivered += 1
    log(f"broadcast streamer=@{streamer_id} event={event.get('type')} delivered={delivered} payload={event}")

def require_secret() -> bool:
    if not SHARED_SECRET:
        return True
    given = request.headers.get("x-bridge-secret", "")
    return given == SHARED_SECRET

# ---- TikTok listener wiring ----
def start_listener_if_needed(streamer_id: str):
    streamer_id = normalize_username(streamer_id)
    if not streamer_id:
        return False

    with lock:
        existing = listeners.get(streamer_id)
        if existing and existing.get("active"):
            log(f"listener already active for @{streamer_id}")
            return True

    def runner():
        try:
            log(f"starting TikTok listener for @{streamer_id}")
            try:
                from TikTokLive import TikTokLiveClient
                from TikTokLive.events import ConnectEvent, DisconnectEvent, CommentEvent, LikeEvent, FollowEvent, GiftEvent, LiveEndEvent
            except Exception as e:
                with lock:
                    listeners[streamer_id] = {
                        "active": False,
                        "startedAt": time.time(),
                        "error": f"ImportError: {e}",
                    }
                log(f"IMPORT ERROR for @{streamer_id}: {e}")
                return

            client = TikTokLiveClient(unique_id=streamer_id)

            @client.on(ConnectEvent)
            async def on_connect(event):
                with lock:
                    listeners[streamer_id] = {
                        "active": True,
                        "startedAt": time.time(),
                        "error": None,
                    }
                log(f"TikTok CONNECTED for @{streamer_id}")
                broadcast(streamer_id, {"type": "status", "state": "connected"})

            @client.on(DisconnectEvent)
            async def on_disconnect(event):
                log(f"TikTok DISCONNECTED for @{streamer_id}")
                broadcast(streamer_id, {"type": "status", "state": "disconnected"})

            @client.on(LiveEndEvent)
            async def on_live_end(event):
                log(f"TikTok LIVE ENDED for @{streamer_id}")
                broadcast(streamer_id, {"type": "status", "state": "ended"})

            @client.on(CommentEvent)
            async def on_comment(event):
                user = getattr(event, "user", None)
                username = getattr(user, "unique_id", None) or getattr(user, "nickname", None) or "unknown"
                text = getattr(event, "comment", "") or ""
                payload = {
                    "type": "comment",
                    "username": str(username),
                    "text": str(text),
                }
                log(f"COMMENT @{streamer_id} from={username} text={text!r}")
                broadcast(streamer_id, payload)

            @client.on(LikeEvent)
            async def on_like(event):
                user = getattr(event, "user", None)
                username = getattr(user, "unique_id", None) or getattr(user, "nickname", None) or "unknown"
                like_count = (
                    getattr(event, "count", None)
                    or getattr(event, "likeCount", None)
                    or getattr(event, "likes", None)
                    or 1
                )
                try:
                    like_count = int(like_count)
                except Exception:
                    like_count = 1
                payload = {
                    "type": "like",
                    "username": str(username),
                    "likeCount": like_count,
                }
                log(f"LIKE @{streamer_id} from={username} count={like_count}")
                broadcast(streamer_id, payload)

            @client.on(FollowEvent)
            async def on_follow(event):
                user = getattr(event, "user", None)
                username = getattr(user, "unique_id", None) or getattr(user, "nickname", None) or "unknown"
                payload = {
                    "type": "follow",
                    "username": str(username),
                }
                log(f"FOLLOW @{streamer_id} from={username}")
                broadcast(streamer_id, payload)

            @client.on(GiftEvent)
            async def on_gift(event):
                user = getattr(event, "user", None)
                username = getattr(user, "unique_id", None) or getattr(user, "nickname", None) or "unknown"

                gift = getattr(event, "gift", None)
                gift_name = getattr(gift, "name", None) or getattr(event, "gift_name", None) or "Gift"

                repeat_count = getattr(event, "repeat_count", None) or getattr(event, "repeatCount", None) or 1
                try:
                    repeat_count = int(repeat_count)
                except Exception:
                    repeat_count = 1

                coin_count = (
                    getattr(event, "diamond_count", None)
                    or getattr(event, "diamondCount", None)
                    or getattr(gift, "diamond_count", None)
                    or getattr(gift, "diamondCount", None)
                    or 1
                )
                try:
                    coin_count = int(coin_count)
                except Exception:
                    coin_count = 1

                payload = {
                    "type": "gift",
                    "username": str(username),
                    "giftName": str(gift_name),
                    "repeatCount": repeat_count,
                    "coinCount": coin_count,
                }
                log(f"GIFT @{streamer_id} from={username} gift={gift_name} repeat={repeat_count} coinCount={coin_count}")
                broadcast(streamer_id, payload)

            client.run()

        except Exception as e:
            with lock:
                listeners[streamer_id] = {
                    "active": False,
                    "startedAt": time.time(),
                    "error": str(e),
                }
            log(f"LISTENER ERROR for @{streamer_id}: {e}")

    thread = threading.Thread(target=runner, name=f"tt-{streamer_id}", daemon=True)
    with lock:
        listeners[streamer_id] = {
            "active": False,
            "startedAt": time.time(),
            "error": None,
            "thread": thread.name,
        }
    thread.start()
    return True

# ---- routes ----
@app.get("/healthz")
def healthz():
    with lock:
        return jsonify({
            "ok": True,
            "pairedRooms": len(pairings),
            "activeSessions": len(sessions),
            "activeStreamers": sum(1 for v in listeners.values() if v.get("active")),
            "listeners": {
                k: {
                    "active": bool(v.get("active")),
                    "error": v.get("error"),
                } for k, v in listeners.items()
            }
        })

@app.route("/pair", methods=["GET", "POST"])
def pair():
    if request.method == "GET":
        room = normalize_room(request.args.get("room", ""))
        html = PAIR_HTML.format(message_block="", room=room, username="")
        return Response(html, mimetype="text/html")

    room = normalize_room(request.form.get("room", ""))
    username = normalize_username(request.form.get("username", ""))

    if not room or not username:
        msg = '<div class="err">Room code and TikTok username are required.</div>'
        return Response(PAIR_HTML.format(message_block=msg, room=room, username=username), mimetype="text/html")

    with lock:
        pairings[room] = {
            "username": username,
            "pairedAt": time.time(),
        }

    log(f"PAIR room={room} -> @{username}")
    msg = f'<div class="ok">Room {room} is now paired to @{username}. Go back to Roblox and press Connect.</div>'
    return Response(PAIR_HTML.format(message_block=msg, room=room, username=username), mimetype="text/html")

@app.post("/session/start")
def session_start():
    if not require_secret():
        return jsonify({"ok": False, "message": "forbidden"}), 403

    data = request.get_json(force=True, silent=True) or {}
    room = normalize_room(data.get("roomCode", ""))
    place_id = data.get("placeId")
    job_id = data.get("jobId")

    log(f"/session/start room={room} placeId={place_id} jobId={job_id}")

    with lock:
        pairing = pairings.get(room)

    if not pairing:
        log(f"/session/start waiting for pair room={room}")
        return jsonify({"ok": False, "message": "room not paired"}), 404

    streamer_id = pairing["username"]
    start_listener_if_needed(streamer_id)

    session_key = uuid.uuid4().hex
    with lock:
        sessions[session_key] = {
            "roomCode": room,
            "streamerId": streamer_id,
            "queue": deque(),
            "createdAt": time.time(),
            "placeId": place_id,
            "jobId": job_id,
        }

    log(f"SESSION CREATED key={session_key[:8]} room={room} streamer=@{streamer_id}")
    return jsonify({
        "ok": True,
        "sessionKey": session_key,
        "roomCode": room,
        "streamerId": streamer_id,
    })

@app.post("/session/stop")
def session_stop():
    if not require_secret():
        return jsonify({"ok": False, "message": "forbidden"}), 403

    data = request.get_json(force=True, silent=True) or {}
    session_key = str(data.get("sessionKey", ""))

    with lock:
        existed = sessions.pop(session_key, None)

    log(f"/session/stop key={session_key[:8]} existed={bool(existed)}")
    return jsonify({"ok": True})

@app.post("/poll")
def poll():
    if not require_secret():
        return jsonify({"ok": False, "message": "forbidden"}), 403

    data = request.get_json(force=True, silent=True) or {}
    session_key = str(data.get("sessionKey", ""))

    with lock:
        session = sessions.get(session_key)

    if not session:
        return jsonify({"ok": False, "message": "invalid session", "events": []}), 404

    events = []
    with lock:
        q: Deque[dict] = session["queue"]
        while q:
            events.append(q.popleft())

    if events:
        log(f"/poll key={session_key[:8]} streamer=@{session['streamerId']} events={len(events)} payload={events}")
    return jsonify({"ok": True, "events": events})

if __name__ == "__main__":
    log(f"starting debug bridge on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
