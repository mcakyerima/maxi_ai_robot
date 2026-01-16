# 🚀 MAXI AI ROBOT - STARTUP GUIDE

## ✅ Prerequisites

1. **Python 3.8+** installed
2. **Virtual Environment** activated
3. **Dependencies** installed: `pip install -r requirements.txt`
4. **Environment Variables** configured (copy `.env.example` to `.env`)

---

## 🎯 How to Start the Application

### **METHOD 1: Using the Startup Script (RECOMMENDED)**

Run from the **project root directory**:

```bash
cd C:\Users\Mc Ak Yerima\Downloads\maxi_project_2025_full\maxi_ai_robot
python start.py
```

This method:
- ✅ Automatically configures Python paths
- ✅ Ensures correct working directory
- ✅ Provides helpful startup messages
- ✅ Handles graceful shutdown

---

### **METHOD 2: Direct UI App Execution**

If you prefer to run the UI app directly:

```bash
cd C:\Users\Mc Ak Yerima\Downloads\maxi_project_2025_full\maxi_ai_robot
python -m ui.app
```

**⚠️ DO NOT run `python app.py` from inside the `ui` folder!**

---

## 🔧 Common Issues & Solutions

### **Issue: "ModuleNotFoundError: No module named 'main'"**

**Cause:** Running the app from the wrong directory.

**Solution:**
```bash
# Navigate to project root
cd C:\Users\Mc Ak Yerima\Downloads\maxi_project_2025_full\maxi_ai_robot

# Run from root
python start.py
```

---

### **Issue: "ModuleNotFoundError: No module named 'ui'"**

**Cause:** Python path not configured correctly.

**Solution:** Always run from project root using `python start.py` or `python -m ui.app`

---

### **Issue: "No module named 'dotenv'"**

**Cause:** Missing dependencies.

**Solution:**
```bash
pip install python-dotenv
# Or install all dependencies:
pip install -r requirements.txt
```

---

### **Issue: Database errors on startup**

**Cause:** Safety system tables not created.

**Solution:** The app will auto-create tables on first run. If issues persist:
```bash
# Delete and recreate database
rm context_memory.db
# Then restart the app
python start.py
```

---

## 📦 Project Structure (Import Reference)

```
maxi_ai_robot/               ← PROJECT ROOT (run from here!)
│
├── start.py                 ← Main startup script (USE THIS)
├── main.py                  ← MaxiAI core logic
├── requirements.txt         ← Dependencies
├── .env                     ← Environment config (create from .env.example)
│
├── ui/                      ← Web interface
│   ├── app.py              ← Flask application
│   ├── socket_server.py    ← WebSocket handler
│   ├── templates/          ← HTML files
│   ├── static/             ← CSS, JS, images
│   └── routes/             ← API routes
│       ├── __init__.py
│       └── parent_routes.py ← Parent dashboard
│
├── brain/                   ← AI logic
│   ├── context_manager/    ← Memory system
│   ├── handlers/           ← LLM handlers
│   ├── safety/             ← Parental controls
│   │   ├── __init__.py
│   │   ├── content_filter.py
│   │   ├── rate_limiter.py
│   │   └── usage_tracker.py
│   └── controller/         ← Finger controller
│
├── voice/                   ← Speech & audio
├── utils/                   ← Utilities
├── common/                  ← Shared code
│   ├── __init__.py
│   └── enums.py            ← AppMode enum
│
└── hardware/               ← Servo control
```

---

## 🌐 Accessing the Application

After starting successfully:

- **Local:** http://localhost:5002
- **Mobile/Tablet (same network):** http://YOUR_COMPUTER_IP:5002
- **Parent Dashboard:** http://localhost:5002/parent-dashboard
  - Default PIN: `1234` (change in `.env` file)

---

## 🛡️ Safety Features Status

On startup, you should see:

```
============================================================
📋 MAXI AI STARTUP STATUS
============================================================
   🧠 Context System: Advanced
   🤖 LLM Provider: GROQ
   🎙️ Speech-to-Text: GROQ
   🤚 Finger Control: Hardware Connected
   ⏰ Listening Timeouts: Enabled
   💾 Memory Database:
      • Short-term: 0 messages
      • Long-term: 0 stored
      • Summaries: 0
      • User Facts: 0
   🛡️ Safety Systems:
      • Content Filter: Active ✓
      • Rate Limiter: Active ✓ (60/hour, 100/session)
      • Usage Tracker: Active ✓
      • Session Timer: Active (60 min)
============================================================
```

---

## 🐛 Debugging Tips

### Check Python Path:
```python
import sys
print("\n".join(sys.path))
```

### Verify Imports:
```python
# From project root
python -c "from main import MaxiAI; print('✅ main.py OK')"
python -c "from common.enums import AppMode; print('✅ common.enums OK')"
python -c "from ui.routes.parent_routes import parent_dashboard_bp; print('✅ routes OK')"
python -c "from brain.safety import get_system_status; print('✅ safety OK')"
```

### Check Database:
```bash
# View database file
ls -l context_memory.db

# Check tables (requires sqlite3)
sqlite3 context_memory.db ".tables"
```

---

## 📝 Environment Variables (.env)

Required variables (copy from `.env.example`):

```env
# Parent Dashboard
PARENT_DASHBOARD_PIN=1234

# LLM Configuration
LLM_PROVIDER=groq
GROQ_API_KEY=your_key_here

# Speech Configuration
TRANSCRIBER_MODE=groq

# Raspberry Pi (for finger control)
RASPBERRY_PI_IP=192.168.31.156
RASPBERRY_PI_PORT=5001

# Timeout Configuration
LISTENING_TIMEOUT_ENABLED=true
DEFAULT_LISTENING_TIMEOUT=20.0
SHORT_LISTENING_TIMEOUT=8.0
WAKE_LISTENING_TIMEOUT=45.0
```

---

## 🎉 Success Indicators

You know the app started successfully when you see:

1. ✅ "Maxi AI Robot is ready!"
2. ✅ All safety systems showing "Active ✓"
3. ✅ Web server running on port 5002
4. ✅ No import errors in console
5. ✅ Can access http://localhost:5002 in browser

---

## 💡 Pro Tips

1. **Always run from project root** - saves headaches
2. **Use virtual environment** - prevents dependency conflicts
3. **Check logs folder** - detailed error logs for debugging
4. **Test parent dashboard** - tap robot face 5 times on menu
5. **Monitor usage stats** - parent dashboard shows learning patterns

---

## 🆘 Still Having Issues?

Check the following files for more info:
- `QUICK_START.md` - Quick setup guide
- `PARENTAL_CONTROLS_GUIDE.md` - Safety features documentation
- `CLOUD_DEPLOYMENT_GUIDE.md` - Railway deployment
- `logs/` folder - Detailed error logs

---

**Last Updated:** January 16, 2026
**Version:** 2.0 (with Safety Features)
