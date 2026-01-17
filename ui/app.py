from ui.routes.parent_routes import parent_dashboard_bp, dashboard_page_bp
from common.enums import AppMode
from main import MaxiAI
import os
import sys
import io
import asyncio
import signal
import threading
from pathlib import Path
from types import FrameType
from typing import Optional
from flask import Flask, render_template, send_from_directory, jsonify, make_response
from flask_socketio import SocketIO
from threading import Thread

# Fix emoji encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add the root directory to Python path FIRST (before importing project modules)
root_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, root_dir)

# Now import from project modules of maxi


app = Flask(__name__,
            static_folder='static',
            template_folder='templates',
            static_url_path='/static')
socketio = SocketIO(app, async_mode='threading')

# Register blueprints
app.register_blueprint(parent_dashboard_bp)
app.register_blueprint(dashboard_page_bp)


class MaxiAIWrapper(MaxiAI):
    """Wrapper to formally declare the loop attribute"""
    loop: Optional[asyncio.AbstractEventLoop] = None


maxi_ai = None
shutdown_event = threading.Event()
maxi_thread = None  # Global thread reference


async def run_maxi_ai():
    """Run MaxiAI main loop"""
    global maxi_ai
    maxi_ai = MaxiAIWrapper()
    maxi_ai.loop = asyncio.get_event_loop()
    await maxi_ai.run()


def start_maxi_ai():
    """Start MaxiAI in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_maxi_ai())
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()


def initialize_maxi_ai():
    """Initialize and start MaxiAI backend thread"""
    global maxi_thread
    if maxi_thread is None or not maxi_thread.is_alive():
        print("🤖 Starting MaxiAI backend thread...")
        maxi_thread = Thread(target=start_maxi_ai, daemon=True)
        maxi_thread.start()
        print("✅ MaxiAI backend thread started")
    return maxi_thread


def graceful_shutdown(signum: int, frame: Optional[FrameType]) -> None:
    """Handle shutdown signals"""
    print("\n🛑 Shutting down gracefully...")
    shutdown_event.set()

    if maxi_ai:
        try:
            # Use MaxiAI's native shutdown method
            maxi_ai.handle_ctrl_c_signal()

            # Ensure cleanup runs
            if maxi_ai.loop and maxi_ai.loop.is_running():
                async def _cleanup():
                    await maxi_ai.cleanup()
                    maxi_ai.loop.stop()
                maxi_ai.loop.create_task(_cleanup())
        except Exception as e:
            print(f"⚠️ Error during shutdown: {e}")

    # Force exit if not completed in 3 seconds
    threading.Timer(3, os._exit, args=[0]).start()

# ======================
# PWA Support Routes
# ======================


@app.route('/manifest.json')
def manifest():
    return send_from_directory('.', 'manifest.json', mimetype='application/manifest+json')


@app.route('/sw.js')
def service_worker():
    response = make_response(send_from_directory('.', 'sw.js'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Service-Worker-Allowed'] = '/'
    return response


@app.route('/offline')
def offline():
    return render_template('offline.html')

# ======================
# Core Application Routes
# ======================


@app.route('/')
def menu():
    """Main entry point that serves the menu page"""
    return render_template('menu.html')


@app.route('/chat')
def chat():
    """Chat interface route"""
    return render_template('chat.html')


@app.route('/math')
def math():
    """Math interface route with PWA headers"""
    response = make_response(render_template('math.html'))
    response.headers['Cache-Control'] = 'no-cache, max-age=0'
    return response


@app.route('/settings')
def settings():
    """Settings page route"""
    return render_template('settings.html')


@app.route('/set_mode/<mode>')
def set_mode(mode):
    """Handle mode changes from the UI"""
    if not maxi_ai:
        return jsonify({"status": "error", "message": "Maxi AI not initialized"})

    mode_map = {
        'general': AppMode.GENERAL_CHAT,
        'math': AppMode.MATH_GESTURE,
        'idle': AppMode.IDLE
    }

    if mode not in mode_map:
        return jsonify({"status": "error", "message": "Invalid mode"})

    asyncio.run_coroutine_threadsafe(
        maxi_ai.set_mode(mode_map[mode]),
        maxi_ai.loop
    )
    return jsonify({
        "status": "success",
        "mode": mode_map[mode].name.lower()
    })

# ======================
# WebSocket Events
# ======================


@socketio.on('connect')
def handle_connect():
    """Handle new WebSocket connections"""
    print('Client connected')
    if maxi_ai and maxi_ai.socket_server:
        # Forward connection events to MaxiAI's socket server
        asyncio.run_coroutine_threadsafe(
            maxi_ai.socket_server._handle_client_connect(),
            maxi_ai.loop
        )


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnections"""
    print('Client disconnected')
    if maxi_ai and maxi_ai.socket_server:
        asyncio.run_coroutine_threadsafe(
            maxi_ai.socket_server._handle_client_disconnect(),
            maxi_ai.loop
        )


@socketio.on('message')
def handle_message(data):
    """Forward WebSocket messages to MaxiAI's socket server"""
    if maxi_ai and maxi_ai.socket_server:
        asyncio.run_coroutine_threadsafe(
            maxi_ai.socket_server._process_message(data),
            maxi_ai.loop
        )

# ======================
# Static File Handling
# ======================


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files with proper caching headers"""
    response = make_response(send_from_directory('static', filename))
    if 'service-worker.js' in filename:
        response.headers['Cache-Control'] = 'no-cache'
    else:
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    return response


# ======================
# Startup Configuration
# ======================
if __name__ == '__main__':
    # Register signal handlers
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # Start MaxiAI in a separate thread
    maxi_thread = Thread(target=start_maxi_ai, daemon=True)
    maxi_thread.start()

    try:
        # Configure and run Flask-SocketIO
        app.config['JSON_AS_ASCII'] = False
        socketio.run(
            app,
            host='0.0.0.0',
            port=5002,
            debug=True,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        graceful_shutdown(signal.SIGINT, None)
    except Exception as e:
        print(f"Web server error: {e}")
        graceful_shutdown(signal.SIGTERM, None)
