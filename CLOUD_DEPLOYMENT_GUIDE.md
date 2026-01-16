# 🚀 Maxi AI Robot - Cloud Deployment Guide

## 📊 Audio Architecture Explanation

### **Critical Audio Flow Update**

#### **Before Cloud Migration (Current Setup)**
```
Edge-TTS (Microsoft) → speaker.py → Laptop Speakers 🔊
```

#### **After Cloud Migration (Updated Architecture)**
```
Edge-TTS (Microsoft) → Cloud Server → WebSocket → Tablet Browser → Tablet Speakers 🔊
```

### **Why This Change is Necessary**

When you deploy to the cloud:
- ❌ Cloud servers don't have speakers
- ❌ The Raspberry Pi might not have speakers (or they're on the robot)
- ✅ **The Android tablet has speakers** and is where the user interacts

**Solution**: Stream audio data from the cloud server to the tablet browser, which plays it using the Web Audio API.

---

## 🎯 Audio Streaming Implementation

### **What We've Added**

1. **`voice/speaker_cloud.py`** - Cloud-optimized TTS engine that streams audio
2. **`ui/static/js/audio_player.js`** - Browser-based audio player
3. **Updated `ui/socket_server.py`** - Added `emit_audio_chunk()` method
4. **Updated `ui/templates/chat.html`** - Integrated audio playback

### **How It Works**

```
1. User asks a question via tablet
2. Cloud server processes with Groq LLM
3. Cloud server calls Edge-TTS (Microsoft)
4. Edge-TTS returns MP3 audio data
5. Server converts to Base64
6. Server sends via WebSocket to tablet
7. Tablet browser decodes and plays audio
8. User hears response through tablet speakers 🔊
```

---

## 📋 Deployment Options Comparison

### **Option 1: Cloud VM (AWS/Azure/DigitalOcean)**

**✅ Best for**: Production deployment, remote access

```
┌──────────────────┐
│ Android Tablet   │ ← User Interface
└────────┬─────────┘
         │ Internet
         ▼
┌────────────────────┐
│ Cloud VM           │ ← Backend Logic
│ Flask + AI + TTS   │
└────────┬───────────┘
         │ Internet
         ▼
┌────────────────────┐
│ Raspberry Pi       │ ← Hardware Control
│ Servo Controller   │
└────────────────────┘
```

**Pros:**
- ✅ Works from anywhere
- ✅ Professional deployment
- ✅ Easy to scale
- ✅ HTTPS support

**Cons:**
- ⚠️ Monthly cost (~$15)
- ⚠️ Requires internet on Pi & tablet

**Cost**: $10-20/month

---

### **Option 2: Raspberry Pi Only**

**✅ Best for**: Cost-free, local network only

```
┌──────────────────┐
│ Android Tablet   │
└────────┬─────────┘
         │ Local Network (WiFi)
         ▼
┌───────────────────────────┐
│ Raspberry Pi (All-in-One) │
│ ┌───────────────────────┐ │
│ │ Flask + AI + TTS      │ │
│ │ Servo Controller      │ │
│ └───────────────────────┘ │
└───────────────────────────┘
```

**Pros:**
- ✅ Zero cloud costs
- ✅ Low latency (local network)
- ✅ Complete independence from laptop

**Cons:**
- ⚠️ Only works on local network
- ⚠️ Pi needs 4GB+ RAM

**Cost**: $0/month

---

### **Option 3: Platform-as-a-Service (Railway/Render/Fly.io)**

**✅ Best for**: Quick deployment, beginners, MVP

```
┌──────────────────┐
│ Android Tablet   │
└────────┬─────────┘
         │ Internet
         ▼
┌───────────────────────────┐
│ Railway/Render/Fly.io     │ ← Managed Platform
│ Auto-deploys from GitHub  │
│ Automatic HTTPS           │
│ Environment variables     │
└────────┬──────────────────┘
         │ Internet
         ▼
┌────────────────────┐
│ Raspberry Pi       │
└────────────────────┘
```

**Pros:**
- ✅ Easiest deployment (< 30 mins)
- ✅ Auto-scaling & monitoring
- ✅ Free tier available
- ✅ GitHub integration
- ✅ Automatic HTTPS
- ✅ Zero server management

**Cons:**
- ⚠️ Less control than VM
- ⚠️ Free tier has limitations (sleep after inactivity)

**Cost**: $0-10/month

---

## 🚀 OPTION 3 DEPLOYMENT: Platform-as-a-Service (Recommended)

### **Why PaaS is Best for You**

1. **No server management** - Focus on your robot, not DevOps
2. **Git-based deployment** - Push code, auto-deploy
3. **Free tier** - Test before committing
4. **Built-in monitoring** - See errors and logs
5. **Auto-restart** - If it crashes, it restarts automatically

---

### **Step-by-Step: Deploy to Railway.app**

#### **1. Prepare Your Project**

First, let's create necessary deployment files:

**Create `Procfile`** (tells Railway how to run your app):
```bash
web: python ui/app.py
```

**Create `railway.json`** (Railway configuration):
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python ui/app.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**Update `requirements.txt`** (ensure all dependencies are listed):
```bash
# Your current requirements.txt is good
# Just ensure these are included:
flask>=2.3.2
flask-socketio>=5.3.4
edge-tts>=7.0.1
groq>=0.4.0
python-dotenv>=1.0.0
websockets>=11.0
```

---

#### **2. Create a GitHub Repository**

```powershell
# In your project directory
cd C:\Users\Mc Ak Yerima\Downloads\maxi_project_2025_full\maxi_ai_robot

# Initialize git (if not already)
git init

# Create .gitignore
@"
__pycache__/
*.pyc
*.pyo
.env
*.log
logs/
shutdown_logs/
intent_cache/
vosk-model-*/
ollama_models/
piper/
.vscode/
"@ | Out-File -FilePath .gitignore -Encoding utf8

# Add files
git add .
git commit -m "Initial commit for cloud deployment"

# Create GitHub repo (via web or CLI)
# Then push
git remote add origin https://github.com/YOUR_USERNAME/maxi-ai-robot.git
git branch -M main
git push -u origin main
```

---

#### **3. Deploy to Railway**

1. **Go to [railway.app](https://railway.app)**
2. **Sign up** with GitHub
3. **Click "New Project"**
4. **Select "Deploy from GitHub repo"**
5. **Choose your `maxi-ai-robot` repository**
6. **Railway will auto-detect Python** and start building

---

#### **4. Configure Environment Variables**

In Railway dashboard:

1. Click your project
2. Go to **"Variables"** tab
3. Add these variables:

```env
GROQ_API_KEY=your_groq_key_here
OPENWEATHER_API_KEY=your_weather_key_here
RASPBERRY_PI_IP=your_pi_public_ip_or_domain
RASPBERRY_PI_PORT=5001
USE_WAKE_WORD=false
AUDIO_CAPTURE_MODE=ui
TRANSCRIBER_MODE=groq
LLM_PROVIDER=groq
GROQ_MODEL=compound-beta-mini
PORT=5002
```

---

#### **5. Get Your Deployment URL**

Railway will provide a URL like:
```
https://maxi-ai-robot-production.up.railway.app
```

**Update your tablet to use this URL** instead of `localhost:5002`

---

#### **6. Configure Raspberry Pi**

##### **Option A: Pi on Same Network (Local)**

If tablet & Pi are on same network, no changes needed to Pi.

##### **Option B: Pi Remote Access (Internet)**

Use **ngrok** to expose Pi's API:

```bash
# On Raspberry Pi
sudo apt install ngrok

# Expose port 5001
ngrok http 5001

# Copy the ngrok URL (e.g., https://abc123.ngrok.io)
# Update Railway environment variable:
# RASPBERRY_PI_IP=abc123.ngrok.io
# RASPBERRY_PI_PORT=443
```

**OR** use **Tailscale** (better for permanent setup):

```bash
# On Raspberry Pi
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# On your laptop (or cloud server)
# Install Tailscale and connect
# Pi will have a permanent address like: 100.x.x.x
```

---

### **Alternative: Deploy to Render.com**

1. **Go to [render.com](https://render.com)**
2. **Sign up with GitHub**
3. **New → Web Service**
4. **Connect your GitHub repo**
5. **Configure**:
   - **Name**: `maxi-ai-robot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python ui/app.py`
   - **Instance Type**: Free (or $7/month for always-on)
6. **Add environment variables** (same as Railway)
7. **Create Web Service**

Render will give you a URL like:
```
https://maxi-ai-robot.onrender.com
```

---

### **Alternative: Deploy to Fly.io**

```powershell
# Install Fly CLI
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"

# Login
fly auth login

# Initialize app
cd C:\Users\Mc Ak Yerima\Downloads\maxi_project_2025_full\maxi_ai_robot
fly launch

# Follow prompts:
# - App name: maxi-ai-robot
# - Region: Choose closest to you
# - PostgreSQL: No
# - Redis: No

# Set environment variables
fly secrets set GROQ_API_KEY=your_key_here
fly secrets set OPENWEATHER_API_KEY=your_key_here
fly secrets set RASPBERRY_PI_IP=your_pi_ip

# Deploy
fly deploy

# Your app will be at: https://maxi-ai-robot.fly.dev
```

---

## 🔧 Switching Between Local and Cloud Audio

### **For Development (Local Testing)**

In `main.py`, use the original speaker:

```python
from voice.speaker import SmoothTTSEngine

# In MaxiAI.__init__():
self.tts_engine = SmoothTTSEngine()
```

### **For Cloud Deployment**

In `main.py`, use the cloud speaker:

```python
from voice.speaker_cloud import CloudTTSEngine

# In MaxiAI.__init__():
self.tts_engine = CloudTTSEngine(self.socket_server)
```

**OR** use the **Hybrid Engine** (automatically detects):

```python
from voice.speaker_cloud import HybridTTSEngine
import os

# In MaxiAI.__init__():
mode = "cloud" if os.getenv("DEPLOYMENT_MODE") == "cloud" else "local"
self.tts_engine = HybridTTSEngine(mode=mode, socket_server=self.socket_server)
```

Then add to your `.env`:
```env
# For local development
DEPLOYMENT_MODE=local

# For cloud deployment (set in Railway/Render)
DEPLOYMENT_MODE=cloud
```

---

## 🧪 Testing Audio Streaming

### **Local Test Before Deployment**

1. **Start your app locally**:
   ```powershell
   python ui/app.py
   ```

2. **Open tablet browser**: `http://YOUR_LAPTOP_IP:5002`

3. **Enable cloud mode** temporarily:
   ```python
   # In main.py, force cloud mode
   from voice.speaker_cloud import CloudTTSEngine
   self.tts_engine = CloudTTSEngine(self.socket_server)
   ```

4. **Test a question** - Audio should play from tablet, not laptop

---

## 📊 Platform Comparison

| Feature | Railway | Render | Fly.io | Your VM |
|---------|---------|--------|--------|---------|
| **Free Tier** | ✅ $5 credit | ✅ 750 hrs/month | ✅ Limited | ❌ |
| **Auto-Deploy** | ✅ | ✅ | ✅ | ❌ |
| **HTTPS** | ✅ Auto | ✅ Auto | ✅ Auto | ⚠️ Manual |
| **Setup Time** | 10 mins | 10 mins | 15 mins | 1-2 hours |
| **Learning Curve** | Easy | Easy | Medium | Hard |
| **Control** | Medium | Medium | High | Full |
| **Best For** | Quick MVP | Production | Advanced users | Full control |

**Recommendation**: Start with **Railway** or **Render** for fastest deployment.

---

## 🎯 Post-Deployment Checklist

### **After Deploying to Cloud**

- [ ] App is accessible at cloud URL
- [ ] WebSocket connection works (check browser console)
- [ ] Tablet can load the UI
- [ ] Text-to-speech plays on **tablet speakers** (not server)
- [ ] Raspberry Pi API is reachable from cloud
- [ ] Hand movements work when triggered
- [ ] Environment variables are set correctly
- [ ] Logs show no errors

### **Test Flow**

1. ✅ Open tablet → navigate to cloud URL
2. ✅ Click mic button
3. ✅ Speak a question
4. ✅ See transcription appear
5. ✅ See robot response in chat
6. ✅ **Hear audio from tablet speakers**
7. ✅ See hand gesture (if applicable)

---

## 🐛 Troubleshooting

### **Audio Not Playing**

**Symptoms**: Text appears but no sound

**Solutions**:
1. Check browser console for errors
2. Ensure `audio_player.js` is loaded
3. Verify WebSocket receives `audio_chunk` messages
4. Test audio playback: `audioPlayer.playAudio(testBase64, 'mp3')`
5. Check tablet volume settings

### **WebSocket Connection Fails**

**Symptoms**: "Not connected to server"

**Solutions**:
1. Check if cloud service is running
2. Verify WebSocket port (8765) is exposed
3. Check firewall settings on cloud platform
4. Try WSS (secure WebSocket) if using HTTPS

### **Raspberry Pi Not Responding**

**Symptoms**: Hand movements don't work

**Solutions**:
1. Verify Pi has internet connection
2. Check Pi API is running: `curl http://PI_IP:5001/status`
3. If using ngrok, verify tunnel is active
4. Check `RASPBERRY_PI_IP` environment variable

---

## 💡 Production Recommendations

1. **Use HTTPS** - All platforms provide it automatically
2. **Monitor logs** - Check Railway/Render dashboard regularly
3. **Set up alerts** - Get notified of crashes
4. **Use environment-specific configs** - Different settings for dev/prod
5. **Version control** - Always commit before deploying
6. **Test locally first** - Use cloud speaker mode locally

---

## 📞 Support Resources

- **Railway**: https://railway.app/help
- **Render**: https://render.com/docs
- **Fly.io**: https://fly.io/docs
- **Edge-TTS**: https://github.com/rany2/edge-tts
- **WebSockets**: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API

---

## 🎉 Summary

### **What Changed for Cloud Deployment**

| Component | Before | After |
|-----------|--------|-------|
| **Audio Output** | Laptop speakers | Tablet speakers |
| **TTS Processing** | Edge-TTS → pygame | Edge-TTS → WebSocket → Browser |
| **Deployment** | Laptop required | Cloud server |
| **Access** | Local network only | Internet (global) |

### **Files Modified**

- ✅ `voice/speaker_cloud.py` - New cloud-optimized TTS engine
- ✅ `ui/socket_server.py` - Added audio streaming method
- ✅ `ui/static/js/audio_player.js` - New browser audio player
- ✅ `ui/templates/chat.html` - Integrated audio playback

### **Next Steps**

1. **Choose a platform** (Railway, Render, or Fly.io)
2. **Create GitHub repo**
3. **Deploy to platform**
4. **Configure environment variables**
5. **Test audio playback**
6. **Enjoy your cloud-powered robot!** 🤖🚀

---

**Questions?** Check the troubleshooting section or review the code comments in the new files!
