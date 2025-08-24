# app.py
# Final, stable version using a unified eventlet architecture.

# IMPORTANT: eventlet must be patched at the very top of the entry point
import eventlet
eventlet.monkey_patch()

import os
import logging
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
import hashlib

from downloader import Downloader
from bencode import bdecode, bencode

# --- App Configuration ---
app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet')

# --- Storage Configuration ---
STORAGE_DIR = os.getenv('RENDER_DISK_MOUNT_PATH', '/app/storage')
UPLOAD_DIR = os.path.join(STORAGE_DIR, 'uploads')
DOWNLOAD_DIR = os.path.join(STORAGE_DIR, 'downloads')

app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Create directories on startup to prevent FileNotFoundError
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
    datefmt='%H:%M:%S'
)

# --- Helper Functions ---
def run_download_task(torrent_path, app_socketio):
    try:
        downloader = Downloader(torrent_path, app_socketio)
        downloader.start()
    except Exception as e:
        logging.error(f"Error in download greenlet: {e}", exc_info=True)
    finally:
        if os.path.exists(torrent_path):
            try:
                os.remove(torrent_path)
                logging.info(f"Cleaned up torrent file: {torrent_path}")
            except OSError as e:
                logging.error(f"Error cleaning up torrent file {torrent_path}: {e}")

def get_torrent_info_hash(torrent_path):
    try:
        with open(torrent_path, 'rb') as f:
            meta_info_bytes = f.read()
        meta_info, _ = bdecode(meta_info_bytes)
        info = meta_info[b'info']
        info_hash = hashlib.sha1(bencode(info)).digest().hex()
        return info_hash
    except Exception as e:
        logging.error(f"Could not extract info_hash from {torrent_path}: {e}")
        return None

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'torrent_file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['torrent_file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file and file.filename.endswith('.torrent'):
        filename = secure_filename(file.filename)
        torrent_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(torrent_path)
        time.sleep(0.2)
        
        info_hash = get_torrent_info_hash(torrent_path)
        if not info_hash:
            os.remove(torrent_path)
            return jsonify({'error': 'Could not parse torrent file.'}), 500

        socketio.start_background_task(run_download_task, torrent_path, socketio)
        logging.info(f"Spawned download task for {filename}")

        return jsonify({
            'message': f'Download started for {filename}.',
            'info_hash': info_hash,
            'file_name': filename
        })
    else:
        return jsonify({'error': 'Invalid file type.'}), 400

@app.route('/download/<path:filename>')
def download_file(filename):
    logging.info(f"Browser requested download for: {filename}")
    return send_from_directory(
        app.config['DOWNLOAD_FOLDER'],
        filename,
        as_attachment=True
    )

# NOTE: Do NOT include if __name__ == '__main__' for Gunicorn/production
