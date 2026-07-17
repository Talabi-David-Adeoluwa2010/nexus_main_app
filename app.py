import json
import uuid
import requests
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_classroom_super_secret_key'

# Updated to support the production async engine (Gevent) 
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

# --- MASTER ADMIN CONFIGURATION ---
ADMIN_APP_URL = "https://nexus-admin-app.onrender.com"

# --- DATABASE-FREE IN-MEMORY STORAGE ---
classrooms = {}       # Format: { class_code: { "classname": name, "teacher": username, "members": [] } }
active_sockets = {}   # Format: { socket_id: { "username": username, "room": room, "role": role } }
teacher_accounts = {
    "admin": "admin123"  # Default developer fallback access
}

@app.route('/')
def home():
    return render_template('index.html')

# --- TEACHER AUTH SYSTEM ---
@socketio.on('register_teacher')
def handle_register_teacher(data):
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    activation_code = data.get('activationCode', '').strip()

    if not username or not password or not activation_code:
        emit('auth_response', {'success': False, 'message': 'All registration fields are required.'})
        return

    if username in teacher_accounts:
        emit('auth_response', {'success': False, 'message': 'Username already registered!'})
        return

    # 🔑 FIX: Perform live API lookup against your deployed Admin App validation system
    try:
        response = requests.post(
            f"{ADMIN_APP_URL}/validate_ticket", 
            json={"ticket": activation_code}, 
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            if not result.get("valid"):
                emit('auth_response', {'success': False, 'message': 'Invalid Admin Activation Ticket!'})
                return
        else:
            emit('auth_response', {'success': False, 'message': 'Admin validation server rejected the request.'})
            return
            
    except requests.exceptions.RequestException as e:
        print(f"Connection Error to Admin: {e}")
        emit('auth_response', {'success': False, 'message': 'Admin validation server is offline!'})
        return

    # Ticket is verified, register the teacher account
    teacher_accounts[username] = password
    emit('auth_response', {'success': True, 'action': 'register', 'message': 'Registration successful! Please log in.'})

@socketio.on('login_teacher')
def handle_login_teacher(data):
    identity = data.get('identity', '').strip()
    password = data.get('password', '')

    if identity in teacher_accounts and teacher_accounts[identity] == password:
        emit('auth_response', {'success': True, 'action': 'login', 'username': identity, 'message': f'Welcome back, Instructor {identity}!'})
    else:
        emit('auth_response', {'success': False, 'message': 'Invalid instructor credentials.'})

# --- CLASSROOM CREATION ---
@socketio.on('create_class')
def handle_create_class(data):
    username = data.get('username')
    classname = data.get('classname', '').strip() or "Untitled Session"
    
    class_code = str(uuid.uuid4())[:13].upper()  # Generates XXXX-XXXX-XXXX structure

    classrooms[class_code] = {
        "classname": classname,
        "teacher": username,
        "members": []
    }
    emit('class_created', {'class_code': class_code})

# --- WORKSPACE LOGISTICS & ACTIVE MONITORING ---
@socketio.on('join_class_session')
def handle_join_class(data):
    name = data.get('name', '').strip()
    class_code = data.get('classCode', '').strip()

    # Verification Handshake: Check if student is banned in Master Panel
    try:
        ban_check = requests.get(f"{ADMIN_APP_URL}/api/check_ban/{name}", timeout=3).json()
        if ban_check.get('banned'):
            emit('banned_status', {'message': 'Your account has been blacklisted by the Administrator! Access denied.'})
            return
    except Exception:
        print("Warning: Could not connect to Admin Panel for live ban verification.")

    if class_code not in classrooms:
        emit('join_response', {'success': False, 'message': 'Classroom code not found!'})
        return

    classroom = classrooms[class_code]
    role = 'instructor' if classroom['teacher'] == name else 'student'

    # Save socket tracking data
    active_sockets[request.sid] = {
        "username": name,
        "room": class_code,
        "role": role
    }

    join_room(class_code)

    # Collect existing peers inside room
    existing_members = []
    for sid, info in active_sockets.items():
        if info['room'] == class_code and sid != request.sid:
            existing_members.append({"socket_id": sid, "name": info["username"]})

    classroom['members'].append({"socket_id": request.sid, "name": name})

    emit('join_response', {
        'success': True,
        'classname': classroom['classname'],
        'teacher': classroom['teacher'],
        'existing_members': existing_members
    })

    # Broadcast introduction update
    emit('bounce_message', {'name': 'SYSTEM', 'content': f'{name} joined the room.', 'type': 'text'}, room=class_code)
    
    # Update user lists locally and broadcast
    broadcast_active_users(class_code)

@socketio.on('register_user')
def handle_register_user(data):
    username = data.get('username')
    role = data.get('role', 'student')
    room = data.get('room')
    
    active_sockets[request.sid] = {
        "username": username,
        "room": room,
        "role": role
    }
    broadcast_active_users(room)

# --- SYSTEM WIDE DISCONNECTION RECOVERY ---
@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_sockets:
        user_info = active_sockets[request.sid]
        room = user_info['room']
        username = user_info['username']

        leave_room(room)
        
        if room in classrooms:
            classrooms[room]['members'] = [m for m in classrooms[room]['members'] if m['socket_id'] != request.sid]

        emit('user_left', {'socket_id': request.sid}, room=room)
        emit('bounce_message', {'name': 'SYSTEM', 'content': f'{username} disconnected.', 'type': 'text'}, room=room)
        
        del active_sockets[request.sid]
        broadcast_active_users(room)

# --- REAL-TIME AUDIO, VIDEO, CHAT, EXAM AND SYSTEM BRIDGING ---
@socketio.on('text_message')
def handle_text_message(data):
    room = data.get('room')
    name = data.get('name')
    content = data.get('content')
    msg_type = data.get('type', 'text')

    # Continuous ban verification (prevents mid-session evasion)
    try:
        ban_check = requests.get(f"{ADMIN_APP_URL}/api/check_ban/{name}", timeout=2).json()
        if ban_check.get('banned'):
            emit('banned_status', {'message': 'Your account has been blacklisted during this active session!'})
            disconnect()
            return
    except Exception:
        pass

    # Bounce payloads down to active room members
    emit('bounce_message', {
        'sender_id': request.sid,
        'name': name,
        'content': content,
        'type': msg_type
    }, room=room, include_self=False)

@socketio.on('image_broadcast')
def handle_image_broadcast(data):
    room = data.get('room')
    name = data.get('name')
    image_data = data.get('image_data')

    emit('bounce_message', {
        'sender_id': request.sid,
        'name': name,
        'content': image_data,
        'type': 'image'
    }, room=room, include_self=False)

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    target_id = data.get('target_id')
    signal = data.get('signal')
    emit('webrtc_signal_received', {
        'sender_id': request.sid,
        'signal': signal
    }, room=target_id)

# --- SECURITY SYSTEM CONTROL CENTER ---
@socketio.on('block_user_by_username')
def handle_block_user_by_username(data):
    target_username = data.get('username')
    
    try:
        requests.post(f"{ADMIN_APP_URL}/api/apply_ban", json={"username": target_username}, timeout=3)
    except Exception:
        pass

    sockets_to_kick = [sid for sid, info in active_sockets.items() if info['username'] == target_username]

    for sid in sockets_to_kick:
        emit('forced_kick', {
            'reason': 'Your connection has been terminated. You have been blacklisted by the classroom administrator.'
        }, room=sid)
        
        room_code = active_sockets[sid]['room']
        disconnect(sid)
        if sid in active_sockets:
            del active_sockets[sid]
        broadcast_active_users(room_code)

def broadcast_active_users(room_code):
    if not room_code:
        return
    active_list = []
    for sid, info in active_sockets.items():
        if info['room'] == room_code:
            active_list.append({"username": info["username"], "role": info["role"]})
    emit('update_active_users', {'users': active_list}, room=room_code)

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
