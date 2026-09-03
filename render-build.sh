#!/bin/bash
# Exit on error
set -o errexit

# Install Python dependencies (gevent will build with pre-installed system deps on Render)
pip install -r requirements.txt
