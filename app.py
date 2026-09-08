import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS  # optional; install with `pip install flask-cors`

# ============================================================
# FLASK APP CONFIG
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'AIzaSyBasLelubu8aPurpZieYBWZ1VZwxRqyxsw')

# Enable CORS if frontend is served from a different origin (e.g., Firebase Hosting)
CORS(app)  # remove if not needed

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
# teacher_accounts: {username: password}
teacher_accounts = {"admin": "admin123"}

# pro_activations: {username: {'expiry': 'YYYY-MM-DD', 'activated_at': timestamp}}
pro_activations = {}

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def mask_password(password):
    return '*' * len(password) if password else ''

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
    """Return current state for debugging (use only in development)."""
    safe_accounts = {u: '********' for u in teacher_accounts}  # hide passwords
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

    logger.info(f'Register attempt: username={username}, email={email}')

    if not username or not password:
        logger.warning(f'Register failed: missing fields for {username}')
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    if username in teacher_accounts:
        logger.warning(f'Register failed: username {username} already exists')
        return jsonify({'success': False, 'message': 'Username already registered!'}), 400

    teacher_accounts[username] = password
    logger.info(f'User {username} registered successfully')
    return jsonify({'success': True, 'message': 'Registration successful! You can now log in.'}), 200

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        logger.warning('Login: missing JSON body')
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    logger.info(f'Login attempt: username={username}')

    if username in teacher_accounts and teacher_accounts[username] == password:
        logger.info(f'Login successful for {username}')
        return jsonify({'success': True, 'username': username}), 200

    logger.warning(f'Login failed for {username} (invalid credentials)')
    return jsonify({'success': False, 'message': 'Invalid username or password.'}), 401

@app.route('/api/ai', methods=['POST'])
def api_ai():
    data = request.get_json()
    if not data:
        logger.warning('AI: missing JSON body')
        return jsonify({'response': 'I did not receive a question. Please try again.'}), 400

    query = data.get('query', '').lower().strip()
    logger.info(f'AI query: {query[:50]}...')

    # Simple rule-based responses
    if 'login' in query:
        response = "Click 'Login as Teacher', enter your username and password, or register to create an account."
    elif 'pro' in query or 'pay' in query:
        response = "To pay for Pro: Transfer to Account: 8024300891 - OPay - Talabi Sunny Okunola, then send the receipt to +2348024300891."
    elif 'exam' in query or 'test' in query:
        response = "Teachers can deploy exams using the 'Setup Exam' button. Students will see a live exam modal with a timer."
    elif 'video' in query or 'camera' in query:
        response = "Video features have been removed in this version. Please use the chat and exam tools."
    elif 'health' in query or 'status' in query:
        response = f"Server is running. Teachers: {len(teacher_accounts)}, Pro users: {len(pro_activations)}."
    else:
        response = "Try asking about 'login', 'pro', 'exam', or 'chat'."

    logger.info(f'AI response: {response[:30]}...')
    return jsonify({'response': response}), 200

@app.route('/api/activate_pro', methods=['POST'])
def api_activate_pro():
    data = request.get_json()
    if not data:
        logger.warning('Pro activation: missing JSON body')
        return jsonify({'success': False, 'message': 'Missing JSON body'}), 400

    username = data.get('username', '').strip()
    code = data.get('activation_code', '').strip().upper()

    logger.info(f'Pro activation attempt for {username} with code {code}')

    if not username:
        logger.warning('Pro activation: username missing')
        return jsonify({'success': False, 'message': 'Username required.'}), 400

    # Validate code (e.g., NEXUS-1234)
    if code.startswith('NEXUS-') and len(code) > 6:
        expiry_date = '2026-12-31'  # could be dynamic
        pro_activations[username] = {
            'expiry': expiry_date,
            'activated_at': datetime.utcnow().isoformat(),
            'code': code
        }
        logger.info(f'Pro activated for {username}, expires {expiry_date}')
        return jsonify({
            'success': True,
            'message': 'Pro activated successfully!',
            'expiry': expiry_date
        }), 200
    else:
        logger.warning(f'Pro activation failed for {username}: invalid code')
        return jsonify({'success': False, 'message': 'Invalid activation code.'}), 400

# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(404)
def not_found(e):
    logger.warning(f'404: {request.path}')
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f'500: {e}')
    return jsonify({'error': 'Internal server error'}), 500

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    logger.info(f'Starting Flask server on port {port}')
    app.run(host='0.0.0.0', port=port, debug=False)  # set debug=True for development
