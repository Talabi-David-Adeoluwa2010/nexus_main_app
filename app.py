import os
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_firebase_secret'

logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Master Data
teacher_accounts = {"admin": "admin123"}
pro_users = {}

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
    return jsonify({'response': response}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
