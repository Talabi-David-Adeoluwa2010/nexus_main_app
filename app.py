import os
import json
import uuid
import logging
import requests
import simple_websocket  # CRITICAL FIX: Allows WS upgrade on Render
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_classroom_super_secret_key'

# Disable noisy debug logs
logging.getLogger('engineio').setLevel(logging.ERROR)

# OPTIMIZED SOCKET.IO CONFIGURATION FOR RENDER
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    max_http_buffer_size=10 * 1024 * 1024,
    ping_timeout=60,
    ping_interval=25
)

# MASTER ADMIN CONFIGURATION
ADMIN_APP_URL = os.environ.get("ADMIN_APP_URL", "https://nexus-admin-app-6.onrender.com").rstrip('/')

# PAYMENT DETAILS
PAYMENT_DETAILS = {
    "account_number": "8024300891",
    "bank_name": "OPay",
    "account_name": "Talabi Sunny Okunola",
    "phone": "+2348024300891"
}

# PRO PLAN DURATIONS
PRO_DURATIONS = {
    "1week": 7,
    "2weeks": 14,
    "4weeks": 28,
    "2months": 60,
    "6months": 180,
    "1year": 365
}

# In-memory storage
classrooms = {}
active_sockets = {}
teacher_accounts = {
    "admin": "admin123"
}
pro_users = {}
pending_payments = {}

@app.route('/')
def home():
    return render_template('index.html')

# --- AI BOT RESPONSES ---
AI_RESPONSES = {
    "navigate": "To navigate Nexus Learn: 1) Select your role (Student or Teacher) on the homepage 2) For Students: Enter your name and class code to join 3) For Teachers: Login with credentials or register 4) Use the classroom interface for video, chat, and exams.",
    "login student": "To login as a Student: 1) Click the 'Login as Student' button on homepage 2) Enter your full name 3) Enter the class code provided by your teacher 4) Click 'Join Classroom' to enter the session.",
    "login teacher": "To login as a Teacher: 1) Click 'Login as Teacher' button on homepage 2) Enter your username and password 3) If new, register with a username and password 4) After login, create a class to get a class code for students.",
    "about": "Nexus Learn is a virtual educational classroom portal featuring live video conferencing, real-time chat, image sharing, exam creation/grading, and student management tools. Built for seamless remote learning experiences.",
    "idea": "The core idea behind Nexus Learn is to bridge the gap between physical and virtual classrooms by providing an all-in-one platform where teachers can conduct live sessions, deploy exams, manage students, and track performance in real-time.",
    "best": "Nexus Learn stands out because: 1) Complete classroom solution with video/audio 2) Built-in exam engine with auto-grading 3) Real-time student tracking 4) Secure admin controls 5) Cross-platform compatibility 6) Pro features for enhanced experience.",
    "pay pro": f"To pay for Nexus Pro: 1) Click 'Upgrade to Pro' on homepage 2) Fill in your details 3) Select duration (1 week to 1 year) 4) Transfer payment to: Account: {PAYMENT_DETAILS['account_number']} - {PAYMENT_DETAILS['bank_name']} - {PAYMENT_DETAILS['account_name']} 5) Send receipt to WhatsApp: {PAYMENT_DETAILS['phone']} 6) Receive activation code 7) Enter code to activate.",
    "pro features": "Nexus Pro features include: 6 hours daily usage, 5 picture limit in global chat, exam eligibility every 24 hours, premium interface themes, priority support, advanced analytics, and enhanced classroom controls."
}

# --- TEACHER AUTH SYSTEM (FREE REGISTRATION) ---
@socketio.on('login_teacher')
def handle_login_teacher(data):
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        emit('auth_response', {'success': False, 'message': 'Username and password are required.'})
        return

    if username in teacher_accounts and teacher_accounts[username] == password:
        pro_status = check_pro_status(username)
        emit('auth_response', {
            'success': True, 
            'action': 'login', 
            'username': username, 
            'is_pro': pro_status['is_pro'],
            'pro_expiry': pro_status['expiry_date'],
            'message': 'Login successful!'
        })
    else:
        emit('auth_response', {'success': False, 'message': 'Invalid username or password.'})

@socketio.on('register_teacher')
def handle_register_teacher(data):
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not password:
        emit('auth_response', {'success': False, 'message': 'Username and password are required.'})
        return

    if username in teacher_accounts:
        emit('auth_response', {'success': False, 'message': 'Username already registered!'})
        return

    # FREE REGISTRATION - No activation code required
    teacher_accounts[username] = password
    emit('auth_response', {
        'success': True, 
        'action': 'register', 
        'message': 'Registration successful! You can now log in.'
    })

# --- PRO ACTIVATION SYSTEM ---
def check_pro_status(username):
    if username in pro_users:
        user_pro = pro_users[username]
        expiry = datetime.fromisoformat(user_pro.get('expiry_date', ''))
        if datetime.now() < expiry:
            return {'is_pro': True, 'expiry_date': user_pro['expiry_date'], 'days_left': (expiry - datetime.now()).days}
        else:
            del pro_users[username]
    return {'is_pro': False, 'expiry_date': None, 'days_left': 0}

@socketio.on('request_pro_activation')
def handle_pro_activation_request(data):
    username = data.get('username', '')
    name = data.get('full_name', '')
    phone = data.get('phone', '')
    duration = data.get('duration', '')
    
    if not username or not name or not phone or not duration:
        emit('pro_activation_response', {'success': False, 'message': 'All fields are required.'})
        return
    
    if duration not in PRO_DURATIONS:
        emit('pro_activation_response', {'success': False, 'message': 'Invalid duration selected.'})
        return
    
    request_id = str(uuid.uuid4())[:8].upper()
    pending_payments[request_id] = {
        'username': username,
        'full_name': name,
        'phone': phone,
        'duration': duration,
        'days': PRO_DURATIONS[duration],
        'timestamp': datetime.now().isoformat()
    }
    
    emit('pro_activation_response', {
        'success': True,
        'request_id': request_id,
        'message': 'Payment details generated',
        'payment_details': PAYMENT_DETAILS,
        'duration_days': PRO_DURATIONS[duration]
    })

@socketio.on('confirm_pro_payment')
def handle_pro_payment_confirmation(data):
    request_id = data.get('request_id', '')
    
    if request_id not in pending_payments:
        emit('payment_status_response', {'success': False, 'message': 'Invalid request.'})
        return
    
    emit('payment_status_response', {
        'success': True,
        'status': 'pending',
        'message': f"Dear valued customer, your request is pending. Contact {PAYMENT_DETAILS['phone']} immediately to receive your activation code and send your receipt to the number.",
        'phone': PAYMENT_DETAILS['phone']
    })

@socketio.on('activate_pro_code')
def handle_pro_code_activation(data):
    username = data.get('username', '')
    activation_code = data.get('activation_code', '').strip().upper()
    
    if not username or not activation_code:
        emit('pro_activation_status', {'success': False, 'message': 'Username and activation code are required.'})
        return
    
    # For demo purposes, accept any valid format code
    # In production, you would verify with admin app
    is_valid = False
    duration_days = 30
    
    try:
        response = requests.post(
            f"{ADMIN_APP_URL}/api/verify_pro_code", 
            json={"code": activation_code, "username": username}, 
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        if response.status_code == 200 and response.json().get("valid"):
            is_valid = True
            duration_days = response.json().get("duration_days", 30)
    except Exception as e:
        print(f"Pro code verification failed: {e}")
        # Local fallback - accept any NEXUS-XXXXXXXX format
        if len(activation_code) == 14 and activation_code.startswith("NEXUS-"):
            is_valid = True
            duration_days = 30
    
    if not is_valid:
        emit('pro_activation_status', {'success': False, 'message': 'Invalid Pro activation code! Please contact support.'})
        return
    
    expiry_date = (datetime.now() + timedelta(days=duration_days)).isoformat()
    pro_users[username] = {
        'expiry_date': expiry_date,
        'activated_date': datetime.now().isoformat(),
        'activation_code': activation_code
    }
    
    emit('pro_activation_status', {
        'success': True,
        'message': f'Nexus Pro activated successfully! Valid until {expiry_date}',
        'expiry_date': expiry_date,
        'is_pro': True
    })

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
    
    pro_status = check_pro_status(username)
    
    emit('class_created', {
        'class_code': class_code,
        'is_pro_teacher': pro_status['is_pro']
    })

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

    pro_status = check_pro_status(name)
    
    active_sockets[request.sid] = {
        "username": name,
        "room": class_code,
        "role": role,
        "is_pro": pro_status['is_pro'],
        "pro_expiry": pro_status['expiry_date'],
        "daily_usage_start": datetime.now().isoformat(),
        "images_sent_today": 0,
        "last_exam_submission": None
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
        'is_pro': pro_status['is_pro'],
        'pro_expiry': pro_status['expiry_date']
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
    
    pro_status = check_pro_status(username)
    
    active_sockets[request.sid] = {
        "username": username,
        "room": room,
        "role": role,
        "is_pro": pro_status['is_pro'],
        "pro_expiry": pro_status['expiry_date'],
        "daily_usage_start": datetime.now().isoformat(),
        "images_sent_today": 0,
        "last_exam_submission": None
    }
    broadcast_active_users(room)

# --- PRO RESTRICTION CHECKS ---
def check_pro_restrictions(sid, action_type):
    if sid not in active_sockets:
        return {'allowed': False, 'message': 'User not found.'}
    
    user_info = active_sockets[sid]
    
    # Pro users have no restrictions
    if user_info.get('is_pro'):
        return {'allowed': True}
    
    # Check daily usage limit (6 hours for non-pro)
    if action_type == 'daily_usage':
        usage_start = datetime.fromisoformat(user_info.get('daily_usage_start', datetime.now().isoformat()))
        hours_used = (datetime.now() - usage_start).total_seconds() / 3600
        if hours_used > 6:
            return {'allowed': False, 'message': 'Daily usage limit reached. Wait 24 hours or upgrade to Pro.'}
    
    # Check image limit (5 images per day for non-pro)
    if action_type == 'image_upload':
        images_sent = user_info.get('images_sent_today', 0)
        if images_sent >= 5:
            return {'allowed': False, 'message': 'Image limit reached. Upgrade to Pro for unlimited images.'}
    
    # Check exam limit (once per 24 hours for non-pro)
    if action_type == 'exam_submission':
        last_exam = user_info.get('last_exam_submission')
        if last_exam:
            last_exam_time = datetime.fromisoformat(last_exam)
            if (datetime.now() - last_exam_time).total_seconds() < 86400:
                return {'allowed': False, 'message': 'Exam submission locked. Wait 24 hours or upgrade to Pro.'}
    
    return {'allowed': True}

# --- EXAM SUBMISSION & RESULT FORWARDING ---
@socketio.on('submit_exam')
def handle_submit_exam(data):
    student_name = data.get('student_name') or active_sockets.get(request.sid, {}).get('username', 'Anonymous')
    room_code = data.get('room') or active_sockets.get(request.sid, {}).get('room', '')
    score = data.get('score', 0)
    total_questions = data.get('total_questions', 0)
    answers = data.get('answers', {})

    restriction_check = check_pro_restrictions(request.sid, 'exam_submission')
    if not restriction_check['allowed']:
        emit('exam_submitted_response', {
            'success': False,
            'message': restriction_check['message']
        })
        return

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

    if request.sid in active_sockets:
        active_sockets[request.sid]['last_exam_submission'] = datetime.now().isoformat()

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

# --- IMAGE BROADCAST WITH PRO LIMITS ---
@socketio.on('image_broadcast')
def handle_image_broadcast(data):
    room = data.get('room')
    name = data.get('name')
    image_data = data.get('image_data')

    restriction_check = check_pro_restrictions(request.sid, 'image_upload')
    if not restriction_check['allowed']:
        emit('image_upload_response', {
            'success': False,
            'message': restriction_check['message']
        })
        return

    if request.sid in active_sockets:
        active_sockets[request.sid]['images_sent_today'] = active_sockets[request.sid].get('images_sent_today', 0) + 1

    emit('bounce_message', {
        'sender_id': request.sid,
        'name': name,
        'content': image_data,
        'type': 'image'
    }, room=room, include_self=False)

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

@socketio.on('ai_query')
def handle_ai_query(data):
    query = data.get('query', '').lower().strip()
    
    response = "I'm sorry, I don't understand that question. Please text either navigation, login, the app, Pro features, or payments, and other things related to the app."
    
    if 'navigate' in query or 'how to use' in query:
        response = AI_RESPONSES['navigate']
    elif 'student' in query and ('login' in query or 'log in' in query or 'join' in query):
        response = AI_RESPONSES['login student']
    elif 'teacher' in query and ('login' in query or 'log in' in query or 'register' in query):
        response = AI_RESPONSES['login teacher']
    elif 'about' in query or 'what is' in query:
        response = AI_RESPONSES['about']
    elif 'idea' in query or 'concept' in query or 'purpose' in query:
        response = AI_RESPONSES['idea']
    elif 'best' in query or 'why choose' in query or 'unique' in query:
        response = AI_RESPONSES['best']
    elif 'pay' in query or 'payment' in query or 'cost' in query:
        response = AI_RESPONSES['pay pro']
    elif 'pro feature' in query or 'premium' in query or 'upgrade' in query:
        response = AI_RESPONSES['pro features']
    
    emit('ai_response', {'response': response})

def broadcast_active_users(room_code):
    if not room_code:
        return
    active_list = []
    for sid, info in active_sockets.items():
        if info['room'] == room_code:
            active_list.append({
                "username": info["username"], 
                "role": info["role"],
                "is_pro": info.get('is_pro', False)
            })
    emit('update_active_users', {'users': active_list}, room=room_code)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    socketio.run(app, host='0.0.0.0', port=port)
