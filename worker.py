# worker.py
import eventlet
eventlet.monkey_patch()

import os
import logging
import redis
import json
import time

from downloader import Downloader

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [Worker] - %(message)s',
    datefmt='%H:%M:%S'
)

# --- Redis Configuration ---
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
DOWNLOAD_QUEUE = os.getenv('DOWNLOAD_QUEUE', 'download_jobs')
STATUS_CHANNEL = os.getenv('STATUS_CHANNEL', 'status_updates')
redis_client = redis.from_url(REDIS_URL)

class MockSocketIO:
    """Publishes job status updates to Redis."""
    def __init__(self, client):
        self.client = client

    def emit(self, event, data):
        try:
            message = json.dumps({'event': event, 'data': data})
            self.client.publish(STATUS_CHANNEL, message)
        except Exception as e:
            logging.error(f"Failed to publish to Redis: {e}")

def run_download(torrent_path, mock_socketio):
    """Run downloader and cleanup."""
    try:
        downloader = Downloader(torrent_path, mock_socketio)
        downloader.start()
    except Exception as e:
        logging.error(f"Download failed for {torrent_path}: {e}", exc_info=True)
    finally:
        if os.path.exists(torrent_path):
            try:
                os.remove(torrent_path)
                logging.info(f"Cleaned up torrent file: {torrent_path}")
            except OSError as e:
                logging.error(f"Error cleaning up torrent file {torrent_path}: {e}")

def main():
    """Worker loop listening for jobs."""
    logging.info("Background worker started.")
    mock_socketio = MockSocketIO(redis_client)

    while True:
        try:
            logging.info("Connecting to Redis...")
            pubsub = redis_client.pubsub()
            pubsub.subscribe(DOWNLOAD_QUEUE)
            logging.info(f"Worker is listening for jobs on Redis queue '{DOWNLOAD_QUEUE}'.")

            for message in pubsub.listen():
                if message['type'] == 'message':
                    torrent_path = message['data'].decode('utf-8')
                    logging.info(f"Received job to download: {torrent_path}")
                    eventlet.spawn(run_download, torrent_path, mock_socketio)
                time.sleep(0.1)  # small sleep to reduce CPU usage
        except redis.exceptions.ConnectionError:
            logging.error("Redis connection lost. Reconnecting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logging.error(f"Unexpected error in worker: {e}. Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == '__main__':
    main()
