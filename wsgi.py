from app import app, socketio

socketio.init_app(app, async_mode='threading')

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)