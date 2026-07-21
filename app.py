# MUST BE THE FIRST TWO LINES IN THE FILE TO PREVENT DEADLOCKS
from gevent import monkey
monkey.patch_all()

import os
import json
import uuid
import requests
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_classroom_super_secret_key'

socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

# MASTER ADMIN CONFIGURATION (Defaults to your live Admin Render App)
ADMIN_APP_URL = os.environ.get("ADMIN_APP_URL", "https://nexus-admin-app-5.onrender.com").rstrip('/')

classrooms = {}       
active_sockets = {}   
teacher_accounts = {
    "admin": "admin123"
}

@app.route('/')
def home():
    return render_template('index.html')

# --- TEACHER AUTH SYSTEM (LOGIN & REGISTRATION) ---
@socketio.on('login_teacher')
def handle_login_teacher(data):
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        emit('auth_response', {'success': False, 'message': 'Username and password are required.'})
        return

    if username in teacher_accounts and teacher_accounts[username] == password:
        emit('auth_response', {
            'success': True, 
            'action': 'login', 
            'username': username, 
            'message': 'Login successful!'
        })
    else:
        emit('auth_response', {'success': False, 'message': 'Invalid username or password.'})

@socketio.on('register_teacher')
def handle_register_teacher(data):
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    # Extract ticket from incoming payload
    activation_code = (
        data.get('activationCode') or 
        data.get('activation_ticket') or 
        data.get('activation') or ''
    )
    activation_code = str(activation_code).strip().upper()

    if not username or not password or not activation_code:
        emit('auth_response', {'success': False, 'message': 'All registration fields are required.'})
        return

    if username in teacher_accounts:
        emit('auth_response', {'success': False, 'message': 'Username already registered!'})
        return

    # Enforce exact 14-character format check before querying Admin server
    if len(activation_code) != 14 or not activation_code.startswith("NEXUS-"):
        emit('auth_response', {'success': False, 'message': 'Invalid ticket format. Key must be 14 characters (NEXUS-XXXXXXXX).'})
        return

    # Strictly verify ticket against Admin App API
    is_valid = False
    try:
        response = requests.post(
            f"{ADMIN_APP_URL}/api/verify_code", 
            json={"code": activation_code, "username": username}, 
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        if response.status_code == 200 and response.json().get("valid"):
            is_valid = True
    except Exception as e:
        print(f"Admin App verification failed: {e}")
        emit('auth_response', {'success': False, 'message': 'Unable to connect to Admin verification service. Please try again.'})
        return

    if not is_valid:
        emit('auth_response', {'success': False, 'message': 'Invalid or expired Admin Activation Ticket!'})
        return

    # Save registered account to memory
    teacher_accounts[username] = password
    emit('auth_response', {'success': True, 'action': 'register', 'message': 'Registration successful! You can now log in.'})

# --- CLASSROOM CREATION ---
@socketio.on('create_class')
def handle_create_class(data):
    username = data.get('username')
    classname = data.get('classname', '').strip() or "Untitled Session"
    
    class_code = str(uuid.uuid4())[:13].upper()

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

    if not name or not class_code:
        emit('join_response', {'success': False, 'message': 'Name and Class Code are required.'})
        return

    try:
        ban_check = requests.get(f"{ADMIN_APP_URL}/api/check_ban/{name}", timeout=2).json()
        if ban_check.get('banned'):
            emit('banned_status', {'message': 'Your account has been blacklisted by the Administrator!'})
            return
    except Exception:
        pass

    if class_code not in classrooms:
        emit('join_response', {'success': False, 'message': 'Classroom code not found!'})
        return

    classroom = classrooms[class_code]
    role = 'instructor' if classroom['teacher'] == name else 'student'

    active_sockets[request.sid] = {
        "username": name,
        "room": class_code,
        "role": role
    }

    join_room(class_code)

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

    # Register active session with the admin panel
    try:
        requests.post(f"{ADMIN_APP_URL}/api/register_session_remote", json={
            "username": name,
            "ip": request.remote_addr,
            "sid": request.sid
        }, timeout=2)
    except Exception:
        pass

    emit('bounce_message', {'name': 'SYSTEM', 'content': f'{name} joined the room.', 'type': 'text'}, room=class_code)
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

# --- DISCONNECTION RECOVERY ---
@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_sockets:
        user_info = active_sockets[request.sid]
        room = user_info['room']
        username = user_info['username']

        leave_room(room)
        
        if room in classrooms:
            classrooms[room]['members'] = [m for m in classrooms[room]['members'] if m['socket_id'] != request.sid]

        try:
            requests.post(f"{ADMIN_APP_URL}/api/remove_session_remote", json={"sid": request.sid}, timeout=2)
        except Exception:
            pass

        emit('user_left', {'socket_id': request.sid}, room=room)
        emit('bounce_message', {'name': 'SYSTEM', 'content': f'{username} disconnected.', 'type': 'text'}, room=room)
        
        del active_sockets[request.sid]
        broadcast_active_users(room)

# --- REAL-TIME DATA BRIDGES ---
@socketio.on('text_message')
def handle_text_message(data):
    room = data.get('room')
    name = data.get('name')
    content = data.get('content')
    msg_type = data.get('type', 'text')

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

@socketio.on('block_user_by_username')
def handle_block_user_by_username(data):
    target_username = data.get('username')
    try:
        requests.post(f"{ADMIN_APP_URL}/api/apply_ban_remote", json={"username": target_username}, timeout=2)
    except Exception:
        pass

    sockets_to_kick = [sid for sid, info in active_sockets.items() if info['username'] == target_username]
    for sid in sockets_to_kick:
        emit('forced_kick', {'reason': 'Terminated by classroom administrator.'}, room=sid)
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
    port = int(os.environ.get("PORT", 5001))
    socketio.run(app, host='0.0.0.0', port=port)
