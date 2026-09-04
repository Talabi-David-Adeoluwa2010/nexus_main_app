import os
import logging
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.config['SECRET_KEY'] = 'AIzaSyBasLelubu8aPurpZieYBWZ1VZwxRqyxsw'

logging.getLogger('werkzeug').setLevel(logging.ERROR)

# In‑memory teacher store (demo only; for production use Firebase)
teacher_accounts = {"admin": "admin123"}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400
    if username in teacher_accounts:
        return jsonify({'success': False, 'message': 'Username already registered!'}), 400
    teacher_accounts[username] = password
    return jsonify({'success': True, 'message': 'Registration successful! You can now log in.'}), 200

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if username in teacher_accounts and teacher_accounts[username] == password:
        return jsonify({'success': True, 'username': username}), 200
    return jsonify({'success': False, 'message': 'Invalid username or password.'}), 401

@app.route('/api/ai', methods=['POST'])
def api_ai():
    data = request.get_json()
    query = data.get('query', '').lower().strip()
    response = "I'm sorry, I don't understand that question. Please ask about navigation, login, the app, Pro features, or payments."
    if 'login' in query:
        response = "Click 'Login as Teacher', enter your username and password, or register to create an account."
    elif 'pro' in query or 'pay' in query:
        response = "To pay for Pro: Transfer to Account: 8024300891 - OPay - Talabi Sunny Okunola, then send the receipt to +2348024300891."
    elif 'exam' in query or 'test' in query:
        response = "Teachers can deploy exams using the 'Setup Exam' button. Students will see a live exam modal with a timer."
    elif 'video' in query or 'camera' in query:
        response = "Your video is shared with all participants. Use the controls to mute mic, stop cam, flip or mirror."
    else:
        response = "Try asking about 'login', 'pro', 'exam', or 'video'."
    return jsonify({'response': response}), 200

@app.route('/api/activate_pro', methods=['POST'])
def api_activate_pro():
    data = request.get_json()
    username = data.get('username', '').strip()
    code = data.get('activation_code', '').strip().upper()
    # Demo: accept any code starting with NEXUS- and at least 6 characters
    if code.startswith('NEXUS-') and len(code) > 6:
        return jsonify({'success': True, 'message': 'Pro activated successfully!', 'expiry': '2026-12-31'})
    else:
        return jsonify({'success': False, 'message': 'Invalid activation code.'}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
