# app.py
# This is now just the web server. It handles uploads and relays status updates.

import os
import logging
import threading
import json
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
import redis

# --- App Configuration ---
app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')

# --- Storage Configuration ---
STORAGE_DIR = os.getenv('RENDER_DISK_MOUNT_PATH', 'storage')
UPLOAD_DIR = os.path.join(STORAGE_DIR, 'uploads')
DOWNLOAD_DIR = os.path.join(STORAGE_DIR, 'downloads')

app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_DIR

# Create directories on startup
if not os.path.exists(UPLOAD_DIR): os.makedirs(UPLOAD_DIR)
if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)

# --- Redis Connection ---
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(REDIS_URL)

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [WebApp] - %(message)s',
    datefmt='%H:%M:%S'
)

# --- Redis Listener Thread ---
def redis_listener():
    """Listens for status updates from the worker and relays them to clients."""
    pubsub = redis_client.pubsub()
    pubsub.subscribe('status_updates')
    logging.info("Redis listener started.")
    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                payload = json.loads(message['data'])
                event = payload.get('event')
                data = payload.get('data')
                if event and data:
                    socketio.emit(event, data)
            except (json.JSONDecodeError, TypeError):
                logging.warning(f"Could not decode message from Redis: {message['data']}")

# Start the listener in a background thread when the app starts
threading.Thread(target=redis_listener, daemon=True).start()

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
        
        # Publish a job to the Redis queue for the worker to pick up
        redis_client.publish('download_jobs', torrent_path)
        logging.info(f"Published job for {filename} to Redis.")

        # We need the file_name and info_hash for the UI, so we parse it here quickly
        from bencode import bdecode, bencode
        import hashlib
        try:
            with open(torrent_path, 'rb') as f: meta_info_bytes = f.read()
            meta_info, _ = bdecode(meta_info_bytes)
            info = meta_info[b'info']
            info_hash = hashlib.sha1(bencode(info)).digest().hex()
            file_name_from_torrent = info[b'name'].decode('utf-8')
        except Exception:
            # Fallback if parsing fails
            info_hash = "unknown"
            file_name_from_torrent = filename

        return jsonify({
            'message': f'Download queued for {filename}.',
            'info_hash': info_hash,
            'file_name': file_name_from_torrent
        })
    else:
        return jsonify({'error': 'Invalid file type.'}), 400

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)
