from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import sqlite3
import random
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli-anahtar-degistir'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------- VERİTABANI ----------
def init_db():
    with sqlite3.connect("veri.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                code TEXT PRIMARY KEY
            )
        """)
init_db()

# Aktif kullanıcılar { code: socket_id }
active_users = {}

# ---------- HTTP ROTALARI ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    code = data.get("code", "").strip()
    if not code.isdigit() or len(code) != 8:
        return jsonify({"error": "8 haneli sayı girin"}), 400
    
    with sqlite3.connect("veri.db") as conn:
        cur = conn.execute("SELECT code FROM users WHERE code = ?", (code,))
        if not cur.fetchone():
            conn.execute("INSERT INTO users (code) VALUES (?)", (code,))
    
    return jsonify({"success": True, "code": code})

# ---------- SOCKET.IO OLAYLARI ----------
@socketio.on("register")
def handle_register(data):
    code = data["code"]
    if code in active_users:
        emit("register_error", {"message": "Bu kod zaten çevrimiçi"})
        return
    active_users[code] = request.sid
    print(f"✅ {code} bağlandı. Aktif: {list(active_users.keys())}")

@socketio.on("call_random")
def handle_call_random(data):
    caller = data["from"]
    available = [c for c in active_users.keys() if c != caller]
    if not available:
        emit("random_call_target", {"error": "Çevrimiçi başka kullanıcı yok"}, room=request.sid)
        return
    target = random.choice(available)
    # Arayana hedefi bildir
    emit("random_call_target", {"target": target}, room=request.sid)
    # Hedefe direkt çağrı git (onay yok)
    emit("incoming_call", {"from": caller}, room=active_users[target])

@socketio.on("webrtc_offer")
def handle_offer(data):
    target = data["target"]
    if target in active_users:
        emit("webrtc_offer", {
            "from": data["from"],
            "offer": data["offer"]
        }, room=active_users[target])

@socketio.on("webrtc_answer")
def handle_answer(data):
    target = data["target"]
    if target in active_users:
        emit("webrtc_answer", {
            "from": data["from"],
            "answer": data["answer"]
        }, room=active_users[target])

@socketio.on("ice_candidate")
def handle_ice(data):
    target = data["target"]
    if target in active_users:
        emit("ice_candidate", {
            "from": data["from"],
            "candidate": data["candidate"]
        }, room=active_users[target])

@socketio.on("end_call")
def handle_end_call(data):
    target = data["target"]
    if target in active_users:
        emit("call_ended", room=active_users[target])

@socketio.on("call_error")
def handle_call_error(data):
    target = data.get("target")
    if target and target in active_users:
        emit("call_error", {"message": data.get("message", "Hata")}, room=active_users[target])

@socketio.on("disconnect")
def handle_disconnect():
    for code, sid in list(active_users.items()):
        if sid == request.sid:
            del active_users[code]
            print(f"❌ {code} ayrıldı. Kalan: {list(active_users.keys())}")
            break

# ---------- YAYIN (SNAP DEPLOY, RENDER, RAILWAY) İÇİN ----------
# Gunicorn/eventlet ile çalışması için
application = app

if __name__ == "__main__":
    # Lokal test için
    socketio.run(app, host="0.0.0.0", port=5001, debug=True)