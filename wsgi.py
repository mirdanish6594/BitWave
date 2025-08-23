# wsgi.py
# This is the production entry point for the Gunicorn server.

from app import app, socketio

if __name__ == "__main__":
    # The host must be 0.0.0.0 to be accessible from outside the container
    socketio.run(app, host="0.0.0.0", port=5000)
