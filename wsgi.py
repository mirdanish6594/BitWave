# wsgi.py
# This is the definitive production entry point for the Gunicorn server.
# It ensures the application starts with the correct async mode.

import eventlet
eventlet.monkey_patch()

from app import app, socketio

if __name__ == "__main__":
    # This command is used by Gunicorn to start the app.
    # The host must be 0.0.0.0 to be accessible inside Render's container.
    socketio.run(app, host="0.0.0.0", port=5000)
