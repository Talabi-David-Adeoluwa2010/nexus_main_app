import os
import time
import re
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('app.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================================
# JITSI (JaaS) CONFIGURATION
# ============================================================
JITSI_APP_ID = os.environ.get('JITSI_APP_ID', '').strip()
JITSI_KID = os.environ.get('JITSI_KID', '').strip()

_jitsi_key = os.environ.get('JITSI_PRIVATE_KEY', '')
if _jitsi_key and '\\n' in _jitsi_key and 'BEGIN' in _jitsi_key:
    _jitsi_key = _jitsi_key.replace('\\n', '\n')
if not _jitsi_key:
    _path = os.environ.get('JITSI_PRIVATE_KEY_PATH', '')
    if _path and os.path.exists(_path):
        with open(_path, 'r') as f:
            _jitsi_key = f.read()
JITSI_PRIVATE_KEY = _jitsi_key.strip() if _jitsi_key else ''

JITSI_CONFIGURED = bool(JITSI_APP_ID and JITSI_KID and JITSI_PRIVATE_KEY and pyjwt)

if JITSI_CONFIGURED:
    logger.info('JaaS configured. App ID starts with: %s', JITSI_APP_ID[:24])
else:
    logger.warning('JaaS not fully configured. Video meetings will not work until env vars are set.')


def _build_jitsi_room(classroom_code):
    """Deterministic room name derived from classroom code."""
    slug = ''.join(ch for ch in classroom_code if ch.isalnum()).lower()
    if not slug:
        slug = 'default'
    return 'nexusclass' + slug


# ============================================================
# IN-MEMORY STORES
# ============================================================
teacher_accounts = {"admin": "admin123"}
pro_activations = {}
blocked_users = {}


# ============================================================
# ROUTES
# ============================================================
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'teachers': len(teacher_accounts),
        'pro_users': len(pro_activations),
        'jitsi_configured': JITSI_CONFIGURED,
        'diagnostics': {
            'has_app_id': bool(JITSI_APP_ID),
            'has_kid': bool(JITSI_KID),
            'has_private_key': bool(JITSI_PRIVATE_KEY),
            'private_key_length': len(JITSI_PRIVATE_KEY) if JITSI_PRIVATE_KEY else 0,
            'has_pyjwt': bool(pyjwt),
        }
    }), 200


@app.route('/api/debug', methods=['GET'])
def debug():
    safe_accounts = {u: '********' for u in teacher_accounts}
    return jsonify({
        'teacher_accounts': safe_accounts,
        'pro_activations': pro_activations,
    }), 200


# ---------- AUTH ----------
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    if not USERNAME_RE.match(username):
        return jsonify({
            'success': False,
            'message': 'Username must be 3–32 characters (letters, numbers, _ . -).'
        }), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400

    if email and not EMAIL_RE.match(email):
        return jsonify({'success': False, 'message': 'Please enter a valid email address.'}), 400

    if username in teacher_accounts:
        return jsonify({'success': False, 'message': 'Username already registered!'}), 400

    teacher_accounts[username] = password
    logger.info('User %s registered successfully', username)
    return jsonify({
        'success': True,
        'message': 'Registration successful! You can now log in.'
    }), 200


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    if username in teacher_accounts and teacher_accounts[username] == password:
        logger.info('User %s logged in', username)
        return jsonify({'success': True, 'username': username}), 200

    return jsonify({'success': False, 'message': 'Invalid username or password.'}), 401


# ---------- AI ASSISTANT ----------
@app.route('/api/ai', methods=['POST'])
def api_ai():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'response': 'I did not receive a question. Please try again.'}), 400

    query = (data.get('query') or '').lower().strip()

    if not query:
        response = "Ask me anything about Nexus Learn!"
    elif 'login' in query or 'sign in' in query or 'register' in query:
        response = "Click 'Login as Teacher', enter your username and password, or register to create an account."
    elif 'pro' in query or 'pay' in query or 'upgrade' in query:
        response = "To pay for Pro: Transfer to Account: 8024300891 - OPay - Talabi Sunny Okunola, then send the receipt to +2348024300891."
    elif 'exam' in query or 'test' in query or 'quiz' in query:
        response = "Teachers can deploy exams using the 'Setup Exam' button. Students will see a live exam modal with a timer."
    elif 'video' in query or 'camera' in query or 'meeting' in query or 'call' in query:
        response = "Video meetings are powered by Jitsi. Click 'Join Video' in your classroom, then tap the ⬇️ button to minimize the call and keep using the classroom."
    elif 'health' in query or 'status' in query:
        response = f"Server is running. Teachers: {len(teacher_accounts)}, Pro users: {len(pro_activations)}."
    else:
        response = "Try asking about 'login', 'pro', 'exam', 'video', 'attendance', or 'announce'."

    return jsonify({'response': response}), 200


# ---------- PRO ACTIVATION ----------
@app.route('/api/activate_pro', methods=['POST'])
def api_activate_pro():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    username = (data.get('username') or '').strip()
    code = (data.get('activation_code') or '').strip().upper()

    if not username:
        return jsonify({'success': False, 'message': 'Username required.'}), 400

    if code.startswith('NEXUS-') and len(code) > 6:
        expiry_date = '2026-12-31'
        pro_activations[username] = {
            'expiry': expiry_date,
            'activated_at': datetime.utcnow().isoformat(),
            'code': code
        }
        logger.info('Pro activated for %s', username)
        return jsonify({
            'success': True,
            'message': 'Pro activated successfully!',
            'expiry': expiry_date
        }), 200

    return jsonify({'success': False, 'message': 'Invalid activation code.'}), 400


# ---------- JITSI JWT ----------
@app.route('/api/jitsi/token', methods=['POST'])
def api_jitsi_token():
    if not JITSI_CONFIGURED:
        return jsonify({
            'success': False,
            'message': 'Video service is not configured on the server.'
        }), 500

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    classroom = (data.get('classroom') or '').strip()
    is_teacher = bool(data.get('is_teacher', False))

    if not username or not classroom:
        return jsonify({'success': False, 'message': 'username and classroom are required'}), 400

    room_name = _build_jitsi_room(classroom)
    now = int(time.time())

    payload = {
        'aud': 'jitsi',
        'iss': 'chat',
        'sub': JITSI_APP_ID,
        'room': '*',
        'iat': now,
        'nbf': now - 10,
        'exp': now + 60 * 60,
        'context': {
            'user': {
                'id': username,
                'name': username,
                'email': f'{username}@nexuslearn.local',
                'avatar': '',
                'moderator': is_teacher
            },
            'features': {
                'livestreaming': False,
                'recording': False,
                'transcription': False,
                'outbound-call': False
            }
        }
    }

    try:
        token = pyjwt.encode(
            payload,
            JITSI_PRIVATE_KEY,
            algorithm='RS256',
            headers={'kid': JITSI_KID}
        )
    except Exception as e:
        logger.exception('Failed to sign JaaS token: %s', e)
        return jsonify({'success': False, 'message': 'Token generation failed'}), 500

    return jsonify({
        'success': True,
        'token': token,
        'appId': JITSI_APP_ID,
        'roomName': room_name,
        'domain': '8x8.vc'
    }), 200


# ============================================================
# SOCKET.IO
# ============================================================
@socketio.on('connect')
def handle_connect():
    logger.info('Client connected: %s', request.sid)


@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected: %s', request.sid)


# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    return render_template('index.html'), 200


@app.errorhandler(500)
def internal_error(e):
    logger.exception('Internal server error: %s', e)
    return jsonify({'error': 'Internal server error'}), 500


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    logger.info('Starting Nexus Learn on port %s', port)
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
