#!/bin/bash
# Exit on error
set -o errexit

# Install system dependencies
apt-get update
apt-get install -y gcc python3-dev libevent-dev

# Install Python dependencies
pip install -r requirements.txt
