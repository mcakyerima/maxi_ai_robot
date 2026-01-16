#!/usr/bin/env python3
"""
Maxi AI Robot - Main Startup Script
Run this file from the project root directory to start the application.

Usage:
    python start.py
    
This script ensures proper Python path configuration and starts the Flask web UI
which will automatically initialize the Maxi AI backend.
"""

from ui.app import app, socketio, initialize_maxi_ai
import signal
from ui.app import app, socketio
import os
import sys
from pathlib import Path

# Ensure we're in the project root directory
project_root = Path(__file__).parent.absolute()
os.chdir(project_root)

# Add project root to Python path
sys.path.insert(0, str(project_root))

print("🚀 Starting Maxi AI Robot...")
print(f"📁 Project Root: {project_root}")
print(f"🐍 Python: {sys.version}")
print("-" * 60)

# Verify critical imports before starting
try:
    print("🔍 Verifying project structure...")
    from main import MaxiAI
    print("   ✅ main.py")
    from common.enums import AppMode
    print("   ✅ common.enums")
    from ui.routes.parent_routes import parent_dashboard_bp, dashboard_page_bp
    print("   ✅ ui.routes")
    from brain.safety import get_system_status
    print("   ✅ brain.safety")
    print("   ✅ All core modules verified!")
    print("-" * 60)
except ImportError as e:
    print(f"\n❌ Import Error: {e}")
    print("\nPlease ensure:")
    print("  1. You're running from the project root directory")
    print("  2. All dependencies are installed: pip install -r requirements.txt")
    print("  3. Virtual environment is activated (if using one)")
    sys.exit(1)

# Import Flask app, socketio, and initialization function


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n🛑 Shutting down Maxi AI Robot...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)

if __name__ == '__main__':
    try:
        # Initialize MaxiAI backend thread
        print("-" * 60)
        initialize_maxi_ai()
        print("-" * 60)

        # Get port from environment variable (Railway compatibility) or default to 5002
        port = int(os.getenv('PORT', 5002))
        host = os.getenv('HOST', '0.0.0.0')

        # The app is already configured in ui/app.py
        print(f"✅ Starting web server on {host}:{port}")
        print(f"🌐 Access the app at: http://localhost:{port}")
        if host == '0.0.0.0':
            print(f"📱 Or from mobile: http://<your-computer-ip>:{port}")
        print("-" * 60)
        print("💡 Tip: Press Ctrl+C to stop the server\n")

        # Start the Flask-SocketIO server
        socketio.run(
            app,
            host=host,
            port=port,
            debug=False,  # Always False for production/Railway
            use_reloader=False,  # Must be False for Railway
            allow_unsafe_werkzeug=True,
            log_output=True
        )
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
