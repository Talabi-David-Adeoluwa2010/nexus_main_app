#!/bin/bash
set -o errexit
pip install -r requirements.txt
flask
flask-socketio
requests
