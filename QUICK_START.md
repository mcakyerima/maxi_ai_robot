# 🚀 Quick Start: Deploy Maxi AI to the Cloud

## ⚡ 5-Minute Deployment (Railway.app)

### **Step 1: Push to GitHub** (2 minutes)

```powershell
cd "C:\Users\Mc Ak Yerima\Downloads\maxi_project_2025_full\maxi_ai_robot"

# Initialize git
git init
git add .
git commit -m "Ready for cloud deployment"

# Create repo on GitHub.com, then:
git remote add origin https://github.com/YOUR_USERNAME/maxi-ai-robot.git
git branch -M main
git push -u origin main
```

### **Step 2: Deploy to Railway** (2 minutes)

1. Go to **[railway.app](https://railway.app)** → Sign up with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select **`maxi-ai-robot`** repository
4. Railway auto-detects Python and deploys! ✨

### **Step 3: Add Environment Variables** (1 minute)

In Railway dashboard → **Variables** tab, add:

```env
GROQ_API_KEY=gsk_your_key_here
OPENWEATHER_API_KEY=your_weather_key
RASPBERRY_PI_IP=your_pi_ip
DEPLOYMENT_MODE=cloud
USE_WAKE_WORD=false
TRANSCRIBER_MODE=groq
LLM_PROVIDER=groq
```

### **Step 4: Get Your URL**

Railway provides: `https://maxi-ai-robot-production.up.railway.app`

### **Step 5: Update Tablet**

Open tablet browser and go to your Railway URL!

---

## 🎯 What's Different?

### **Audio Output**
- ❌ **Before**: Audio played on your laptop speakers
- ✅ **After**: Audio plays on **tablet speakers** via WebSocket

### **How It Works**
```
1. Tablet sends question via WebSocket
2. Cloud server processes with Groq
3. Edge-TTS generates audio (Microsoft Cloud)
4. Audio streams to tablet via WebSocket
5. Tablet browser plays audio 🔊
```

---

## 🔧 Files We Created

| File | Purpose |
|------|---------|
| `voice/speaker_cloud.py` | Cloud-optimized TTS engine |
| `ui/static/js/audio_player.js` | Browser audio player |
| `Procfile` | Tells cloud how to run app |
| `railway.json` | Railway configuration |
| `.gitignore` | Files to exclude from git |
| `.env.example` | Environment variables template |
| `CLOUD_DEPLOYMENT_GUIDE.md` | Detailed guide |

---

## ✅ Testing Checklist

After deployment:

- [ ] App loads at cloud URL
- [ ] WebSocket connects (check browser console)
- [ ] Can ask questions via mic
- [ ] **Audio plays from tablet speakers** (not server!)
- [ ] Raspberry Pi responds to hand commands
- [ ] No errors in logs

---

## 🐛 Quick Troubleshooting

### **No Audio?**
- Open browser console (F12)
- Look for "🔊 Received audio chunk" message
- Check tablet volume
- Try refreshing page

### **WebSocket Won't Connect?**
- Verify app is running on Railway
- Check WebSocket port 8765 is exposed
- Try HTTPS URL (Railway auto-provides)

### **Raspberry Pi Not Working?**
- Ensure Pi has internet
- Test: `curl http://YOUR_PI_IP:5001/status`
- Consider using ngrok for remote access

---

## 📚 Full Guide

See **`CLOUD_DEPLOYMENT_GUIDE.md`** for:
- Detailed explanations
- Alternative platforms (Render, Fly.io)
- Raspberry Pi setup
- Production best practices

---

## 🎉 You're Done!

Your robot is now:
- ✅ **Independent of your laptop**
- ✅ **Accessible from anywhere**
- ✅ **Playing audio on the tablet**
- ✅ **Cloud-powered!** 🚀

**Questions?** Check the full deployment guide or project documentation!
