"""
WSGI entry point for Render deployment.
This file is used by Gunicorn to start the application.
"""
from app import app, socketio

# Initialize SocketIO with async_mode='threading' for compatibility with standard Gunicorn workers
socketio.init_app(app, async_mode='threading')

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
