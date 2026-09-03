# MUST BE THE FIRST TWO LINES IN THE FILE TO PREVENT DEADLOCKS
from gevent import monkey
monkey.patch_all()

import os
import json
import uuid
import logging
import requests
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_classroom_super_secret_key'

# Disable noisy debug logs to save system resources during image streaming
logging.getLogger('engineio').setLevel(logging.ERROR)

# OPTIMIZED SOCKET.IO CONFIGURATION
socketio = SocketIO(
    app, 
    async_mode='gevent', 
    cors_allowed_origins="*",
    max_http_buffer_size=10 * 1024 * 1024,  # 10 MB Buffer
    ping_timeout=60,                       # 60s timeout before dropping client
    ping_interval=25                       # 25s ping interval
)

# MASTER ADMIN CONFIGURATION
ADMIN_APP_URL = os.environ.get("ADMIN_APP_URL", "https://nexus-admin-app-6.onrender.com").rstrip('/')

# PAYMENT DETAILS
PAYMENT_DETAILS = {
    "account_number": "8024300891",
    "bank_name": "OPay",
    "account_name": "Talabi Sunny Okunola",
    "contact_number": "+2348024300891"
}

classrooms = {}       
active_sockets = {}   
teacher_accounts = {
    "admin": "admin123"
}

# PRO USER DATABASE (In production, use a proper database)
pro_users = {}
activation_codes = {}

# AI BOT RESPONSES
AI_BOT_RESPONSES = {
    "how to navigate": "To navigate NEXUS LEARN: 1) After the loading page, you'll see the homepage with buttons for Student and Teacher login. 2) Click the appropriate button based on your role. 3) For students, enter your name and class code. 4) For teachers, login with your credentials and create a class session. 5) Use the controls at the bottom to manage your camera, microphone, and chat.",
    "how to login as a teacher": "To login as a teacher: 1) On the homepage, click the 'Login as Teacher' button. 2) Enter your username and password. 3) If you don't have an account, click 'Register as instructor' and fill in the required fields including your activation ticket. 4) After successful login, you'll see the Instructor Hub where you can create class sessions.",
    "how to login as a student": "To login as a student: 1) On the homepage, click the 'Login as Student' button. 2) Enter your full name and the class code provided by your teacher. 3) Click 'Join Classroom'. 4) You'll be connected to your virtual classroom with video, chat, and exam features.",
    "about the app": "NEXUS LEARN is a comprehensive virtual educational classroom portal founded by Talabi David Adeoluwa. It provides real-time video conferencing, interactive chat, dynamic exam creation, gradebook tracking, and secure teacher-student communication. The app is designed to make online learning engaging and accessible.",
    "the idea of the app": "The idea behind NEXUS LEARN is to create a secure, feature-rich virtual classroom environment that bridges the gap between physical and online education. It enables teachers to conduct live classes, administer exams, track student progress, and maintain classroom discipline remotely - all in one unified platform.",
    "why the app is the best for you": "NEXUS LEARN stands out because: 1) It's completely FREE for basic use. 2) Features real-time video with optimized bandwidth for smooth connections. 3) Includes dynamic exam engines with OBJ and theory support. 4) Provides teacher controls for classroom management. 5) Has built-in gradebook tracking. 6) Offers Nexus Pro for advanced features like extended hours and more.",
    "how to pay for the nexus pro": "To pay for Nexus Pro: 1) Click 'Activate Nexus Pro' button on the homepage. 2) Fill in your name and phone number. 3) Select your preferred duration (1 week to 1 year). 4) You'll see the payment details - transfer to OPay account 8024300891 (Talabi Sunny Okunola). 5) After payment, contact +2348024300891 with your receipt to receive your activation code. 6) Enter the activation code on the homepage to unlock Pro features.",
    "features of the nexus pro": "NEXUS PRO features include: 1) Extended 6-hour daily usage limit. 2) Send up to 5 pictures in global chat. 3) Exam setting available every 24 hours. 4) Premium background theme. 5) Priority video streaming quality. 6) Advanced classroom analytics. 7) Priority support access. 8) Exclusive Pro badges and features.",
}

@app.route('/')
def home():
    return render_template('index.html')

# --- PAYMENT & ACTIVATION SYSTEM ---
@socketio.on('submit_payment_request')
def handle_payment_request(data):
    try:
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        duration = data.get('duration', '').strip()
        
        if not name or not phone or not duration:
            emit('payment_response', {'success': False, 'message': 'All fields are required.'})
            return
        
        # Send payment request to admin app for processing
        try:
            response = requests.post(
                f"{ADMIN_APP_URL}/api/payment_request",
                json={
                    "name": name,
                    "phone": phone,
                    "duration": duration,
                    "account_details": PAYMENT_DETAILS
                },
                timeout=5
            )
        except Exception as e:
            print(f"Payment request forwarding failed: {e}")
        
        emit('payment_response', {
            'success': True,
            'payment_details': PAYMENT_DETAILS,
            'message': 'Payment details retrieved successfully'
        })
    except Exception as e:
        emit('payment_response', {'success': False, 'message': 'Error processing payment request.'})

@socketio.on('verify_pro_activation')
def handle_pro_activation(data):
    code = data.get('activation_code', '').strip().upper()
    username = data.get('username', '').strip()
    
    if not code or not username:
        emit('pro_activation_response', {'success': False, 'message': 'Activation code and username are required.'})
        return
    
    # Check if code is valid format
    if not code.startswith("NEXUS-PRO-"):
        emit('pro_activation_response', {'success': False, 'message': 'Invalid activation code format.'})
        return
    
    # Check if already used
    if code in activation_codes and activation_codes[code].get('used'):
        emit('pro_activation_response', {'success': False, 'message': 'This activation code has already been used.'})
        return
    
    # Verify with admin app
    is_valid = False
    try:
        response = requests.post(
            f"{ADMIN_APP_URL}/api/verify_pro_code", 
            json={"code": code, "username": username},
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        if response.status_code == 200 and response.json().get("valid"):
            is_valid = True
    except Exception as e:
        print(f"Admin verification failed: {e}")
    
    if not is_valid:
        emit('pro_activation_response', {'success': False, 'message': 'Invalid or expired activation code.'})
        return
    
    # Activate pro for user
    activation_codes[code] = {
        'used': True,
        'username': username,
        'activated_at': datetime.now().isoformat()
    }
    
    pro_users[username] = {
        'activated': True,
        'activation_date': datetime.now().isoformat(),
        'code': code
    }
    
    emit('pro_activation_response', {
        'success': True,
        'message': 'Nexus Pro activated successfully! Enjoy your premium features.'
    })

@socketio.on('check_pro_status')
def handle_pro_status(data):
    username = data.get('username', '').strip()
    is_pro = username in pro_users and pro_users[username].get('activated', False)
    emit('pro_status_response', {'is_pro': is_pro})

# --- AI BOT QUERY HANDLER ---
@socketio.on('ai_bot_query')
def handle_ai_bot_query(data):
    query = data.get('query', '').strip().lower()
    
    # Find best matching response
    best_response = "I'm sorry, I don't understand that question. Please ask about navigation, login, app features, Nexus Pro, or payment."
    
    for key, response in AI_BOT_RESPONSES.items():
        if key in query:
            best_response = response
            break
    
    emit('ai_bot_response', {'response': best_response})

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

    if len(activation_code) != 14 or not activation_code.startswith("NEXUS-"):
        emit('auth_response', {'success': False, 'message': 'Invalid ticket format. Key must be 14 characters total (NEXUS-XXXXXXXX).'})
        return

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

    teacher_accounts[username] = password
    emit('auth_response', {
        'success': True, 
        'action': 'register', 
        'message': 'Registration successful! You can now log in.'
    })

# --- CLASSROOM CREATION ---
@socketio.on('create_class')
def handle_create_class(data):
    username = data.get('username')
    classname = data.get('classname', '').strip() or "Untitled Session"
    
    # Check if pro user for exam limits
    is_pro = username in pro_users and pro_users[username].get('activated', False)
    
    # Check exam eligibility for non-pro users
    if not is_pro:
        if username in teacher_accounts:
            last_exam = teacher_accounts[username].get('last_exam_time')
            if last_exam:
                time_diff = datetime.now() - datetime.fromisoformat(last_exam)
                if time_diff < timedelta(hours=24):
                    hours_left = 24 - (time_diff.seconds // 3600)
                    emit('exam_eligibility', {
                        'eligible': False,
                        'message': f'You must wait {hours_left} hours before setting another exam. Upgrade to Pro for unlimited exam setting!',
                        'is_pro': False
                    })
                    return
    
    class_code = str(uuid.uuid4())[:13].upper()

    classrooms[class_code] = {
        "classname": classname,
        "teacher": username,
        "members": [],
        "is_pro": is_pro,
        "created_at": datetime.now().isoformat()
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
    
    # Check pro status and daily usage
    is_pro = name in pro_users and pro_users[name].get('activated', False)
    daily_usage_key = f"daily_usage_{name}_{datetime.now().strftime('%Y-%m-%d')}"
    
    if not is_pro and daily_usage_key in active_sockets:
        emit('join_response', {'success': False, 'message': 'Free users are limited to 6 hours daily. Upgrade to Pro for extended access!'})
        return

    active_sockets[request.sid] = {
        "username": name,
        "room": class_code,
        "role": role,
        "is_pro": is_pro,
        "joined_at": datetime.now().isoformat(),
        "daily_usage_key": daily_usage_key
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
        'existing_members': existing_members,
        'is_pro': is_pro,
        'is_pro_classroom': classroom.get('is_pro', False)
    })

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
        "role": role,
        "is_pro": username in pro_users and pro_users[username].get('activated', False),
        "joined_at": datetime.now().isoformat(),
        "daily_usage_key": f"daily_usage_{username}_{datetime.now().strftime('%Y-%m-%d')}"
    }
    broadcast_active_users(room)

# --- EXAM SUBMISSION & RESULT FORWARDING ---
@socketio.on('submit_exam')
def handle_submit_exam(data):
    student_name = data.get('student_name') or active_sockets.get(request.sid, {}).get('username', 'Anonymous')
    room_code = data.get('room') or active_sockets.get(request.sid, {}).get('room', '')
    score = data.get('score', 0)
    total_questions = data.get('total_questions', 0)
    answers = data.get('answers', {})

    payload = {
        "student_name": student_name,
        "room_code": room_code,
        "score": score,
        "total_questions": total_questions,
        "answers": answers
    }

    admin_saved = False
    try:
        resp = requests.post(
            f"{ADMIN_APP_URL}/api/receive_exam_result",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        if resp.status_code == 200:
            admin_saved = True
    except Exception as e:
        print(f"Failed to submit results to Admin URL: {e}")

    emit('exam_submitted_response', {
        'success': True,
        'message': 'Your exam was submitted successfully!',
        'admin_saved': admin_saved
    })

    emit('bounce_message', {
        'name': 'SYSTEM',
        'content': f'{student_name} submitted their exam (Score: {score}/{total_questions}).',
        'type': 'text'
    }, room=room_code)

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
    
    # Check pro status for image limit
    user_info = active_sockets.get(request.sid, {})
    is_pro = user_info.get('is_pro', False)
    
    if not is_pro:
        # Free users limited to 3 images per session
        image_count = user_info.get('image_count', 0)
        if image_count >= 3:
            emit('image_limit_reached', {'message': 'Free users can only send 3 images. Upgrade to Pro for 5 images!'})
            return
        user_info['image_count'] = image_count + 1
        active_sockets[request.sid] = user_info
    else:
        # Pro users limited to 5 images
        image_count = user_info.get('image_count', 0)
        if image_count >= 5:
            emit('image_limit_reached', {'message': 'You have reached the maximum of 5 images for this session.'})
            return
        user_info['image_count'] = image_count + 1
        active_sockets[request.sid] = user_info

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
            active_list.append({
                "username": info["username"], 
                "role": info["role"],
                "is_pro": info.get("is_pro", False)
            })
    emit('update_active_users', {'users': active_list}, room=room_code)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    socketio.run(app, host='0.0.0.0', port=port)
