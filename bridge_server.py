import os
import threading
import time
import uuid
from collections import defaultdict, deque
from html import escape

from flask import Flask, jsonify, request, Response
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, FollowEvent, GiftEvent, LikeEvent

SHARED_SECRET = os.getenv('SHARED_SECRET', 'CHANGE_ME')
SESSION_TTL_SECONDS = int(os.getenv('SESSION_TTL_SECONDS', '1800'))
PAIRING_TTL_SECONDS = int(os.getenv('PAIRING_TTL_SECONDS', '21600'))
MAX_EVENTS_PER_SESSION = int(os.getenv('MAX_EVENTS_PER_SESSION', '500'))
MAX_POLL_BATCH = int(os.getenv('MAX_POLL_BATCH', '25'))

app = Flask(__name__)
lock = threading.RLock()

clients = {}
stream_sessions = defaultdict(set)
sessions = {}
room_pairings = {}


def now_ts() -> float:
    return time.time()


def normalize_streamer_id(value: str) -> str:
    return (value or '').strip().lstrip('@').lower()


def normalize_room_code(value: str) -> str:
    cleaned = ''.join(ch for ch in (value or '').strip().upper() if ch.isalnum() or ch in '-_')
    return cleaned[:32]


def require_secret() -> bool:
    return request.headers.get('x-bridge-secret') == SHARED_SECRET


def cleanup_expired():
    cutoff_sessions = now_ts() - SESSION_TTL_SECONDS
    cutoff_pairings = now_ts() - PAIRING_TTL_SECONDS
    with lock:
        for session_key in list(sessions.keys()):
            if sessions[session_key]['last_activity'] < cutoff_sessions:
                remove_session_unlocked(session_key)
        for room_code, pairing in list(room_pairings.items()):
            if pairing['updated_at'] < cutoff_pairings:
                room_pairings.pop(room_code, None)


def push_event(streamer_id: str, payload: dict):
    with lock:
        for session_key in list(stream_sessions.get(streamer_id, set())):
            session = sessions.get(session_key)
            if not session:
                continue
            session['queue'].append(payload)
            session['last_activity'] = now_ts()


class StreamClientState:
    def __init__(self, streamer_id: str):
        self.streamer_id = streamer_id
        self.client = TikTokLiveClient(unique_id=f'@{streamer_id}')
        self.thread = None
        self.started = False
        self.last_error = None
        self.connected = False
        self.created_at = now_ts()
        self.last_activity = now_ts()
        self._wire_events()

    def _wire_events(self):
        client = self.client
        streamer_id = self.streamer_id

        @client.on(ConnectEvent)
        async def _on_connect(event: ConnectEvent):
            self.connected = True
            self.last_activity = now_ts()
            push_event(streamer_id, {'type': 'status', 'state': 'connected', 'streamerId': streamer_id})

        @client.on(DisconnectEvent)
        async def _on_disconnect(event: DisconnectEvent):
            self.connected = False
            self.last_activity = now_ts()
            push_event(streamer_id, {'type': 'status', 'state': 'disconnected', 'streamerId': streamer_id})

        @client.on(GiftEvent)
        async def _on_gift(event: GiftEvent):
            self.last_activity = now_ts()
            repeat_count = getattr(event.gift, 'repeat_count', 1) or 1
            push_event(streamer_id, {
                'type': 'gift',
                'streamerId': streamer_id,
                'username': getattr(event.user, 'nickname', 'TikTok User'),
                'giftName': getattr(event.gift, 'name', 'Gift'),
                'repeatCount': int(repeat_count),
            })

        @client.on(LikeEvent)
        async def _on_like(event: LikeEvent):
            self.last_activity = now_ts()
            push_event(streamer_id, {
                'type': 'like',
                'streamerId': streamer_id,
                'username': getattr(event.user, 'nickname', 'TikTok User'),
                'likeCount': int(getattr(event, 'count', 1) or 1),
            })

        @client.on(FollowEvent)
        async def _on_follow(event: FollowEvent):
            self.last_activity = now_ts()
            push_event(streamer_id, {
                'type': 'follow',
                'streamerId': streamer_id,
                'username': getattr(event.user, 'nickname', 'TikTok User'),
            })

    def _run_forever(self):
        try:
            self.client.run(fetch_gift_info=True)
        except Exception as exc:
            self.last_error = str(exc)
            self.connected = False
            print(f'TikTok client stopped for @{self.streamer_id}: {exc}', flush=True)

    def ensure_started(self):
        if self.started:
            return
        self.thread = threading.Thread(target=self._run_forever, daemon=True)
        self.thread.start()
        self.started = True
        print(f'Started TikTok listener for @{self.streamer_id}', flush=True)


def ensure_stream_client(streamer_id: str) -> StreamClientState:
    with lock:
        state = clients.get(streamer_id)
        if state is None:
            state = StreamClientState(streamer_id)
            clients[streamer_id] = state
        state.ensure_started()
        return state


def remove_session_unlocked(session_key: str):
    session = sessions.pop(session_key, None)
    if not session:
        return None
    stream_sessions[session['streamer_id']].discard(session_key)
    return session


def pairing_snapshot(room_code: str):
    pairing = room_pairings.get(room_code)
    if not pairing:
        return None
    return {'roomCode': room_code, 'streamerId': pairing['streamer_id'], 'updatedAt': pairing['updated_at']}


@app.before_request
def _cleanup():
    cleanup_expired()


@app.get('/')
def index():
    with lock:
        return jsonify({
            'ok': True,
            'service': 'tiktok-roblox-roomcode-pairing-bridge',
            'pairingPage': '/pair',
            'activeStreamers': len(clients),
            'activeSessions': len(sessions),
            'pairedRooms': len(room_pairings),
        })


@app.get('/healthz')
def healthz():
    with lock:
        return jsonify({'ok': True, 'activeStreamers': len(clients), 'activeSessions': len(sessions), 'pairedRooms': len(room_pairings)})


PAIR_HTML = """<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>TikTok Roblox Pairing</title>
  <style>
    :root { color-scheme: dark; }
    body { font-family: Arial, sans-serif; background:#0f1117; color:#fff; margin:0; }
    .wrap { max-width:540px; margin:32px auto; padding:24px; background:#171b26; border:1px solid #2d3447; border-radius:16px; }
    h1 { margin-top:0; font-size:28px; }
    p { color:#c9d1e5; line-height:1.5; }
    label { display:block; margin:16px 0 6px; font-weight:700; }
    input { width:100%; box-sizing:border-box; padding:14px; border-radius:10px; border:1px solid #333b52; background:#0f1320; color:white; font-size:16px; }
    button { margin-top:18px; width:100%; padding:14px; border:none; border-radius:10px; background:#6d5efc; color:white; font-size:16px; font-weight:700; cursor:pointer; }
    .note { margin-top:16px; padding:12px; border-radius:10px; background:#111828; color:#b8c2d8; }
    .ok { margin-top:16px; padding:12px; border-radius:10px; background:#11321e; color:#b6f3c9; }
    .err { margin-top:16px; padding:12px; border-radius:10px; background:#341616; color:#ffc0c0; }
    .small { font-size:13px; color:#8ea0c9; }
    code { background:#0d1220; padding:2px 6px; border-radius:6px; }
  </style>
</head>
<body>
  <div class='wrap'>
    <h1>Pair TikTok Live to Roblox</h1>
    <p>Enter the <strong>room code</strong> shown inside the Roblox game, then enter the TikTok live username to connect this room to that live.</p>
    <form method='post' action='/pair'>
      <label>Room code</label>
      <input name='roomCode' value='__ROOM__' maxlength='32' placeholder='example: ROOM123' required />
      <label>TikTok username</label>
      <input name='streamerId' value='__STREAMER__' placeholder='example: alwald925' required />
      <button type='submit'>Pair now</button>
    </form>
    __MESSAGE__
    <div class='note'>
      <div>How to use:</div>
      <ol>
        <li>Open the game and enter a room code.</li>
        <li>Open this page on your phone.</li>
        <li>Pair the same room code to your TikTok username.</li>
        <li>Back in Roblox, press <code>Connect</code>.</li>
      </ol>
      <div class='small'>This demo stores pairings in memory on Render. If the free instance sleeps or redeploys, pair again.</div>
    </div>
  </div>
</body>
</html>"""


def render_pair_page(room_code='', streamer_id='', message_html=''):
    html = PAIR_HTML.replace('__ROOM__', escape(room_code or ''))
    html = html.replace('__STREAMER__', escape(streamer_id or ''))
    html = html.replace('__MESSAGE__', message_html)
    return Response(html, mimetype='text/html')


@app.get('/pair')
def pair_page():
    room_code = normalize_room_code(request.args.get('room') or request.args.get('roomCode') or '')
    return render_pair_page(room_code=room_code)


@app.post('/pair')
def pair_submit():
    data = request.get_json(silent=True)
    if data is None:
        data = request.form
    room_code = normalize_room_code((data or {}).get('roomCode') or (data or {}).get('room_code'))
    streamer_id = normalize_streamer_id((data or {}).get('streamerId') or (data or {}).get('streamer_id'))
    if not room_code:
        msg = "<div class='err'>Room code is required.</div>"
        return render_pair_page(room_code=room_code, streamer_id=streamer_id, message_html=msg), 400
    if not streamer_id:
        msg = "<div class='err'>TikTok username is required.</div>"
        return render_pair_page(room_code=room_code, streamer_id=streamer_id, message_html=msg), 400
    ensure_stream_client(streamer_id)
    with lock:
        room_pairings[room_code] = {'streamer_id': streamer_id, 'updated_at': now_ts()}
    if request.is_json:
        return jsonify({'ok': True, 'roomCode': room_code, 'streamerId': streamer_id})
    msg = f"<div class='ok'>Room <strong>{escape(room_code)}</strong> is now paired to <strong>@{escape(streamer_id)}</strong>. Go back to Roblox and press Connect.</div>"
    return render_pair_page(room_code=room_code, streamer_id=streamer_id, message_html=msg)


@app.get('/pairing/<room_code>')
def pairing_status(room_code):
    room_code = normalize_room_code(room_code)
    with lock:
        pairing = pairing_snapshot(room_code)
    if not pairing:
        return jsonify({'ok': False, 'paired': False, 'roomCode': room_code}), 404
    return jsonify({'ok': True, 'paired': True, **pairing})


@app.post('/session/start')
def session_start():
    if not require_secret():
        return jsonify({'error': 'unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    room_code = normalize_room_code(payload.get('roomCode') or payload.get('room_code'))
    if not room_code:
        return jsonify({'error': 'roomCode is required'}), 400
    with lock:
        pairing = room_pairings.get(room_code)
    if not pairing:
        return jsonify({'error': 'roomCode is not paired', 'pairUrl': f'/pair?room={room_code}'}), 404
    streamer_id = pairing['streamer_id']
    ensure_stream_client(streamer_id)
    session_key = uuid.uuid4().hex
    with lock:
        sessions[session_key] = {
            'streamer_id': streamer_id,
            'room_code': room_code,
            'created_at': now_ts(),
            'last_activity': now_ts(),
            'queue': deque(maxlen=MAX_EVENTS_PER_SESSION),
            'place_id': str(payload.get('placeId', '')),
            'job_id': str(payload.get('jobId', '')),
        }
        stream_sessions[streamer_id].add(session_key)
    return jsonify({'ok': True, 'sessionKey': session_key, 'streamerId': streamer_id, 'roomCode': room_code, 'pairUrl': f'/pair?room={room_code}'})


@app.post('/session/stop')
def session_stop():
    if not require_secret():
        return jsonify({'error': 'unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    session_key = payload.get('sessionKey') or payload.get('session_key')
    room_code = normalize_room_code(payload.get('roomCode') or payload.get('room_code'))
    removed = None
    with lock:
        if session_key:
            removed = remove_session_unlocked(session_key)
        elif room_code:
            for existing_key, session in list(sessions.items()):
                if session['room_code'] == room_code:
                    removed = remove_session_unlocked(existing_key)
                    break
    return jsonify({'ok': removed is not None})


@app.post('/room/unpair')
def room_unpair():
    if not require_secret():
        return jsonify({'error': 'unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    room_code = normalize_room_code(payload.get('roomCode') or payload.get('room_code'))
    if not room_code:
        return jsonify({'error': 'roomCode is required'}), 400
    removed = False
    with lock:
        if room_code in room_pairings:
            room_pairings.pop(room_code, None)
            removed = True
    return jsonify({'ok': removed})


@app.post('/poll')
def poll():
    if not require_secret():
        return jsonify({'error': 'unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    session_key = payload.get('sessionKey') or payload.get('session_key')
    if not session_key:
        return jsonify({'error': 'sessionKey is required'}), 400
    with lock:
        session = sessions.get(session_key)
        if not session:
            return jsonify({'error': 'session not found'}), 404
        session['last_activity'] = now_ts()
        events = []
        while session['queue'] and len(events) < MAX_POLL_BATCH:
            events.append(session['queue'].popleft())
        pairing = pairing_snapshot(session['room_code'])
    return jsonify({'ok': True, 'events': events, 'streamerId': session['streamer_id'], 'roomCode': session['room_code'], 'paired': pairing is not None})


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    app.run(host='0.0.0.0', port=port)
