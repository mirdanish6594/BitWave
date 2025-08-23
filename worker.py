# worker.py
# This is a dedicated background worker process.
# Its only job is to listen for download jobs on a Redis queue and execute them.

import os
import logging
import asyncio
import redis
import json

from downloader import Downloader

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [Worker] - %(message)s',
    datefmt='%H:%M:%S'
)

# --- Redis Connection ---
# Render provides the REDIS_URL environment variable automatically.
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(REDIS_URL)

class MockSocketIO:
    """
    A mock SocketIO object that publishes messages to a Redis channel
    instead of emitting them over a WebSocket.
    """
    def __init__(self, client):
        self.client = client

    def emit(self, event, data):
        # We publish the event and data as a JSON string to the 'status_updates' channel
        message = json.dumps({'event': event, 'data': data})
        self.client.publish('status_updates', message)
        logging.debug(f"Published to Redis: {message}")

async def main():
    """The main worker loop."""
    logging.info("Background worker started. Listening for jobs on Redis...")
    mock_socketio = MockSocketIO(redis_client)
    pubsub = redis_client.pubsub()
    pubsub.subscribe('download_jobs')

    for message in pubsub.listen():
        if message['type'] == 'message':
            torrent_path = message['data'].decode('utf-8')
            logging.info(f"Received job to download: {torrent_path}")
            
            try:
                # We run the existing downloader logic here.
                # It will use the MockSocketIO to send progress back via Redis.
                downloader = Downloader(torrent_path, mock_socketio)
                await downloader.start()
            except Exception as e:
                logging.error(f"Download failed for {torrent_path}: {e}", exc_info=True)
            finally:
                # Clean up the torrent file after the download attempt is finished
                if os.path.exists(torrent_path):
                    try:
                        os.remove(torrent_path)
                        logging.info(f"Cleaned up torrent file: {torrent_path}")
                    except OSError as e:
                        logging.error(f"Error cleaning up torrent file {torrent_path}: {e}")

if __name__ == '__main__':
    asyncio.run(main())
