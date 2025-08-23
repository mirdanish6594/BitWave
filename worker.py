# worker.py
# This is a dedicated background worker process.
# Its only job is to listen for download jobs on a Redis queue and execute them.

import os
import logging
import asyncio
import redis
import json
import time

# IMPORTANT: eventlet must be patched at the very top of the entry point
import eventlet
eventlet.monkey_patch()

from downloader import Downloader

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [Worker] - %(message)s',
    datefmt='%H:%M:%S'
)

# --- Redis Connection ---
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(REDIS_URL)

class MockSocketIO:
    """
    A mock SocketIO object that publishes messages to a Redis channel.
    """
    def __init__(self, client):
        self.client = client

    def emit(self, event, data):
        try:
            message = json.dumps({'event': event, 'data': data})
            self.client.publish('status_updates', message)
        except Exception as e:
            logging.error(f"Failed to publish to Redis: {e}")

async def main():
    """The main worker loop with a resilient connection."""
    logging.info("Background worker started.")
    mock_socketio = MockSocketIO(redis_client)
    
    while True:
        try:
            logging.info("Connecting to Redis...")
            pubsub = redis_client.pubsub()
            pubsub.subscribe('download_jobs')
            logging.info("Worker is listening for jobs on Redis.")
            
            for message in pubsub.listen():
                if message['type'] == 'message':
                    torrent_path = message['data'].decode('utf-8')
                    logging.info(f"Received job to download: {torrent_path}")
                    
                    try:
                        downloader = Downloader(torrent_path, mock_socketio)
                        await downloader.start()
                    except Exception as e:
                        logging.error(f"Download failed for {torrent_path}: {e}", exc_info=True)
                    finally:
                        if os.path.exists(torrent_path):
                            try:
                                os.remove(torrent_path)
                                logging.info(f"Cleaned up torrent file: {torrent_path}")
                            except OSError as e:
                                logging.error(f"Error cleaning up torrent file {torrent_path}: {e}")
        except redis.exceptions.ConnectionError:
            logging.error("Redis connection lost. Reconnecting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logging.error(f"An unexpected error occurred in the worker: {e}. Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == '__main__':
    asyncio.run(main())
