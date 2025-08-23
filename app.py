# app.py
# Main Flask application with SocketIO for real-time updates.

import os
import logging
import threading
import asyncio
# --- NEW: Import send_from_directory ---
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
import hashlib

from downloader import Downloader
from bencode import bdecode, bencode

# --- App Configuration ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads' # Define download folder
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
socketio = SocketIO(app, async_mode='threading')

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
    datefmt='%H:%M:%S'
)

# --- Helper Functions ---
def start_download_in_background(torrent_path, app_socketio):
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            downloader = Downloader(torrent_path, app_socketio)
            loop.run_until_complete(downloader.start())
        except Exception as e:
            logging.error(f"Error in download thread: {e}", exc_info=True)
        finally:
            loop.close()

    thread = threading.Thread(target=run_loop, name=f"Downloader-{os.path.basename(torrent_path)}")
    thread.start()
    logging.info(f"Started download for {os.path.basename(torrent_path)} in background.")

def get_torrent_info_hash(torrent_path):
    try:
        with open(torrent_path, 'rb') as f:
            meta_info_bytes = f.read()
        meta_info, _ = bdecode(meta_info_bytes)
        info = meta_info[b'info']
        info_hash = hashlib.sha1(bencode(info)).digest()
        return info_hash.hex()
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
        
        info_hash = get_torrent_info_hash(torrent_path)
        if not info_hash:
            os.remove(torrent_path)
            return jsonify({'error': 'Could not parse torrent file.'}), 500

        start_download_in_background(torrent_path, socketio)

        os.remove(torrent_path)
        return jsonify({
            'message': f'Download started for {filename}.',
            'info_hash': info_hash,
            'file_name': filename
        })
    else:
        return jsonify({'error': 'Invalid file type.'}), 400

# --- NEW: Route to serve the completed files ---
@app.route('/download/<path:filename>')
def download_file(filename):
    """Serves a completed file from the downloads directory."""
    logging.info(f"Browser requested download for: {filename}")
    return send_from_directory(
        app.config['DOWNLOAD_FOLDER'],
        filename,
        as_attachment=True # This tells the browser to save the file
    )

# --- Main Entry Point ---
if __name__ == '__main__':
    if not os.path.exists('uploads'): os.makedirs('uploads')
    if not os.path.exists('downloads'): os.makedirs('downloads')
        
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
