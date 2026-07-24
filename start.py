#!/usr/bin/env python3
"""
Maxi AI Robot — startup script (v2).

Launches the new brain: `maxi.server` (Flask + Socket.IO gateway) which runs the
async Orchestrator on its own thread and serves the tablet PWA.

Usage:
    python start.py            # or: python -m maxi.server
"""
import os
import sys
from pathlib import Path

# UTF-8 stdout so emoji logs don't crash on Windows (cp1252) consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

project_root = Path(__file__).parent.absolute()
os.chdir(project_root)
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    print("🚀 Starting Maxi AI Robot (v2)...")
    print(f"📁 Project Root: {project_root}")
    print("-" * 60)
    try:
        from maxi.server import main
    except ImportError as exc:
        print(f"\n❌ Import Error: {exc}")
        print("Ensure deps are installed:  pip install -r requirements.txt")
        sys.exit(1)
    main()
