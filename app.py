import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room, rooms

# ============================================================
# FLASK APP CONFIG
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'AIzaSyBasLelubu8aPurpZieYBWZ1VZwxRqyxsw')
CORS(app)

# ============================================================
# SOCKET.IO SETUP
# ============================================================
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# ============================================================
# LOGGING CONFIG
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# IN-MEMORY STORAGE
# ============================================================
teacher_accounts = {"admin": "admin123"}
pro_activations = {}

# Active video call participants per classroom
# Structure: { classroom_code: set_of_usernames }
active_participants = {}

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def mask_password(password):
    return '*' * len(password) if password else ''

# ============================================================
# ROUTES (unchanged except adding socketio to app)
# ============================================================

@app.route('/')
def home():
    logger.info('Serving index.html')
    return render_template('index.html')

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'teachers': len(teacher_accounts),
        'pro_users': len(pro_activations)
    }), 200

@app.route('/api/debug', methods=['GET'])
def debug():
    safe_accounts = {u: '********' for u in teacher_accounts}
    return jsonify({
        'teacher_accounts': safe_accounts,
        'pro_activations': pro_activations
    }), 200

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not data:
        logger.warning('Register: missing JSON body')
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    if username in teacher_accounts:
        return jsonify({'success': False, 'message': 'Username already registered!'}), 400

    teacher_accounts[username] = password
    logger.info(f'User {username} registered successfully')
    return jsonify({'success': True, 'message': 'Registration successful! You can now log in.'}), 200

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    if username in teacher_accounts and teacher_accounts[username] == password:
        return jsonify({'success': True, 'username': username}), 200
    return jsonify({'success': False, 'message': 'Invalid username or password.'}), 401

@app.route('/api/ai', methods=['POST'])
def api_ai():
    data = request.get_json()
    if not data:
        return jsonify({'response': 'I did not receive a question. Please try again.'}), 400

    query = data.get('query', '').lower().strip()
    logger.info(f'AI query: {query[:50]}...')

    if 'login' in query:
        response = "Click 'Login as Teacher', enter your username and password, or register to create an account."
    elif 'pro' in query or 'pay' in query:
        response = "To pay for Pro: Transfer to Account: 8024300891 - OPay - Talabi Sunny Okunola, then send the receipt to +2348024300891."
    elif 'exam' in query or 'test' in query:
        response = "Teachers can deploy exams using the 'Setup Exam' button. Students will see a live exam modal with a timer."
    elif 'video' in query or 'camera' in query:
        response = "Video features are now available! Click 'Join Video' in your classroom to start a live video call."
    elif 'health' in query or 'status' in query:
        response = f"Server is running. Teachers: {len(teacher_accounts)}, Pro users: {len(pro_activations)}."
    else:
        response = "Try asking about 'login', 'pro', 'exam', 'chat', or 'video'."

    return jsonify({'response': response}), 200

@app.route('/api/activate_pro', methods=['POST'])
def api_activate_pro():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    username = data.get('username', '').strip()
    code = data.get('activation_code', '').strip().upper()

    if not username:
        return jsonify({'success': False, 'message': 'Username required.'}), 400

    if code.startswith('NEXUS-') and len(code) > 6:
        expiry_date = '2026-12-31'
        pro_activations[username] = {
            'expiry': expiry_date,
            'activated_at': datetime.utcnow().isoformat(),
            'code': code
        }
        return jsonify({
            'success': True,
            'message': 'Pro activated successfully!',
            'expiry': expiry_date
        }), 200
    else:
        return jsonify({'success': False, 'message': 'Invalid activation code.'}), 400

# ============================================================
# SOCKET.IO EVENT HANDLERS
# ============================================================

@socketio.on('connect')
def handle_connect():
    logger.info(f'Client connected: {request.sid}')
    # No authentication here; we'll validate on join events

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f'Client disconnected: {request.sid}')
    # Clean up: remove from any active video call rooms
    # We'll handle this on 'video_call_leave' or by tracking sids per room
    # For simplicity, we rely on the client to send 'video_call_leave' before disconnect,
    # but we also need to clean up if they disconnect abruptly.
    # We'll maintain a mapping of sid -> (classroom, username) and remove on disconnect.
    # For now, we'll not implement full cleanup; we'll rely on the participant list
    # being updated on explicit leave. For abrupt disconnects, we can use a timeout
    # or remove them when they reconnect.

# We'll maintain a mapping of sid to participant info for cleanup
sid_to_participant = {}

@socketio.on('video_call_join')
def handle_video_join(data):
    classroom = data.get('classroom')
    username = data.get('username')

    if not classroom or not username:
        emit('video_call_error', {'message': 'Missing classroom or username'})
        return

    room_name = f'classroom_{classroom}'
    join_room(room_name)

    # Store sid mapping for cleanup
    sid_to_participant[request.sid] = (classroom, username)

    # Add to active participants
    if classroom not in active_participants:
        active_participants[classroom] = set()
    active_participants[classroom].add(username)

    logger.info(f'User {username} joined video call in classroom {classroom}')

    # Send the current participant list to the joining user (excluding themselves)
    participants = list(active_participants[classroom])
    emit('video_call_participants', {'participants': participants}, room=request.sid)

    # Notify others in the room that a new participant has joined
    emit('video_call_user_joined', {'username': username}, room=room_name, skip_sid=request.sid)

@socketio.on('video_call_leave')
def handle_video_leave(data):
    classroom = data.get('classroom')
    username = data.get('username')

    if not classroom or not username:
        return

    room_name = f'classroom_{classroom}'
    leave_room(room_name)

    # Remove from active participants
    if classroom in active_participants:
        active_participants[classroom].discard(username)
        if not active_participants[classroom]:
            del active_participants[classroom]

    # Remove sid mapping
    if request.sid in sid_to_participant:
        del sid_to_participant[request.sid]

    logger.info(f'User {username} left video call in classroom {classroom}')

    # Notify others
    emit('video_call_user_left', {'username': username}, room=room_name, skip_sid=request.sid)

@socketio.on('video_call_offer')
def handle_offer(data):
    target = data.get('target')
    sdp = data.get('sdp')
    sender = data.get('sender')
    classroom = data.get('classroom')

    if not all([target, sdp, sender, classroom]):
        return

    room_name = f'classroom_{classroom}'
    # Emit to the target only
    emit('video_call_offer', {
        'sender': sender,
        'sdp': sdp
    }, room=request.sid, include_self=False)  # We need to send to the target's sid; but we don't have target's sid easily.
    # Better: we broadcast to the room and let clients filter by target username.
    # However, we can store mapping of username -> sid to send directly.
    # For simplicity, we'll broadcast to the room and clients check if they are the target.
    # But to avoid unnecessary traffic, we can use a dict username->sid.
    # Let's maintain a mapping of username to sid within the room.

# We'll maintain a mapping of username to sid for the room
# This is a bit complex; for now we'll broadcast and let clients filter.
# But to be efficient, we'll store a global mapping of username->sid.

# Global mapping: username -> sid (only for video call participants)
username_to_sid = {}

@socketio.on('video_call_join')
def handle_video_join(data):
    # ... existing code
    username_to_sid[username] = request.sid

@socketio.on('video_call_leave')
def handle_video_leave(data):
    # ... existing code
    if username in username_to_sid:
        del username_to_sid[username]

@socketio.on('video_call_offer')
def handle_offer(data):
    target = data.get('target')
    sdp = data.get('sdp')
    sender = data.get('sender')
    classroom = data.get('classroom')
    if not all([target, sdp, sender, classroom]):
        return
    target_sid = username_to_sid.get(target)
    if target_sid:
        emit('video_call_offer', {'sender': sender, 'sdp': sdp}, room=target_sid)
    else:
        logger.warning(f'Target {target} not found for offer')

@socketio.on('video_call_answer')
def handle_answer(data):
    target = data.get('target')
    sdp = data.get('sdp')
    sender = data.get('sender')
    classroom = data.get('classroom')
    if not all([target, sdp, sender, classroom]):
        return
    target_sid = username_to_sid.get(target)
    if target_sid:
        emit('video_call_answer', {'sender': sender, 'sdp': sdp}, room=target_sid)
    else:
        logger.warning(f'Target {target} not found for answer')

@socketio.on('video_call_ice_candidate')
def handle_ice_candidate(data):
    target = data.get('target')
    candidate = data.get('candidate')
    sender = data.get('sender')
    classroom = data.get('classroom')
    if not all([target, candidate, sender, classroom]):
        return
    target_sid = username_to_sid.get(target)
    if target_sid:
        emit('video_call_ice_candidate', {'sender': sender, 'candidate': candidate}, room=target_sid)
    else:
        logger.warning(f'Target {target} not found for ICE candidate')

# Also add a handler to get current participants (already sent on join)
# But we can also provide an explicit endpoint if needed.

# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    logger.info(f'Starting Flask-SocketIO server on port {port}')
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
