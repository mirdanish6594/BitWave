# app.py
# This is now just the web server. It handles uploads and relays status updates.

import os
import logging
import json
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
import redis
import time

# --- App Configuration ---
app = Flask(__name__)
# The async_mode must be 'eventlet' to match our production server
socketio = SocketIO(app, async_mode='eventlet')

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

# --- Redis Listener (runs in a background greenlet) ---
def redis_listener():
    """Listens for status updates from the worker and relays them to clients."""
    while True:
        try:
            pubsub = redis_client.pubsub()
            pubsub.subscribe('status_updates')
            logging.info("Redis listener connected and subscribed.")
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
        except redis.exceptions.ConnectionError:
            logging.error("Redis connection lost in listener. Reconnecting in 5s...")
            time.sleep(5)
        except Exception as e:
            logging.error(f"Unexpected error in Redis listener: {e}. Restarting in 5s...")
            time.sleep(5)

# Start the listener in a background greenlet managed by eventlet
socketio.start_background_task(redis_listener)

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
        
        redis_client.publish('download_jobs', torrent_path)
        logging.info(f"Published job for {filename} to Redis.")

        from bencode import bdecode, bencode
        import hashlib
        try:
            with open(torrent_path, 'rb') as f: meta_info_bytes = f.read()
            meta_info, _ = bdecode(meta_info_bytes)
            info = meta_info[b'info']
            info_hash = hashlib.sha1(bencode(info)).digest().hex()
            file_name_from_torrent = info[b'name'].decode('utf-8')
        except Exception:
            info_hash = "unknown-" + filename
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

# NOTE: The if __name__ == '__main__': block is intentionally removed.
# The server is now started via the wsgi.py file.
