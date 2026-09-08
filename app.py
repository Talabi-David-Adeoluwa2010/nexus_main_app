import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# ============================================================
# FLASK APP CONFIG
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'AIzaSyBasLelubu8aPurpZieYBWZ1VZwxRqyxsw')
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('app.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================================
# IN-MEMORY STORAGE
# ============================================================
teacher_accounts = {"admin": "admin123"}
pro_activations = {}

# ============================================================
# ROUTES
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
    return jsonify({'teacher_accounts': safe_accounts, 'pro_activations': pro_activations}), 200

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400
    if username in teacher_accounts:
        return jsonify({'success': False, 'message': 'Username already registered!'}), 400
    teacher_accounts[username] = password
    logger.info(f'User {username} registered')
    return jsonify({'success': True, 'message': 'Registration successful!'}), 200

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
    if 'login' in query:
        response = "Click 'Login as Teacher', enter your username and password, or register."
    elif 'pro' in query or 'pay' in query:
        response = "To pay for Pro: Transfer to Account: 8024300891 - OPay - Talabi Sunny Okunola, then send receipt."
    elif 'exam' in query or 'test' in query:
        response = "Teachers can deploy exams using the 'Setup Exam' button. Students see a live exam modal."
    elif 'video' in query or 'camera' in query:
        response = "Your video is shared with all participants. Use controls to mute mic, stop cam, flip or mirror."
    elif 'health' in query or 'status' in query:
        response = f"Server running. Teachers: {len(teacher_accounts)}, Pro users: {len(pro_activations)}."
    else:
        response = "Try asking about 'login', 'pro', 'exam', or 'video'."
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
        pro_activations[username] = {'expiry': expiry_date, 'activated_at': datetime.utcnow().isoformat(), 'code': code}
        return jsonify({'success': True, 'message': 'Pro activated successfully!', 'expiry': expiry_date}), 200
    else:
        return jsonify({'success': False, 'message': 'Invalid activation code.'}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f'500: {e}')
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
