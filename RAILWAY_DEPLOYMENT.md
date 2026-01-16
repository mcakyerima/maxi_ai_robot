# 🚂 Railway Deployment Guide - Maxi AI Robot

Complete step-by-step guide to deploy Maxi AI to Railway with all features working.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Prepare Your Project](#prepare-your-project)
3. [Deploy to Railway](#deploy-to-railway)
4. [Configure Environment Variables](#configure-environment-variables)
5. [Connect Raspberry Pi to Railway](#connect-raspberry-pi-to-railway)
6. [Test the Deployment](#test-the-deployment)
7. [Troubleshooting](#troubleshooting)
8. [Post-Deployment Checklist](#post-deployment-checklist)

---

## 1. Prerequisites

Before deploying, ensure you have:

- ✅ **GitHub Account** (for code repository)
- ✅ **Railway Account** (sign up at https://railway.app)
- ✅ **Groq API Key** (for LLM and Speech-to-Text)
- ✅ **Raspberry Pi** (optional, for finger control hardware)
- ✅ **Parent Dashboard PIN** (default: 1234, change in production)

---

## 2. Prepare Your Project

### Step 2.1: Create a GitHub Repository

```bash
# Navigate to project root
cd C:\Users\Mc Ak Yerima\Downloads\maxi_project_2025_full\maxi_ai_robot

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Maxi AI Robot with safety features"

# Create a new repository on GitHub (https://github.com/new)
# Then connect and push:
git remote add origin https://github.com/YOUR_USERNAME/maxi-ai-robot.git
git branch -M main
git push -u origin main
```

### Step 2.2: Verify Required Files

Ensure these files exist in your project root:

✅ **`requirements.txt`** - All Python dependencies
✅ **`start.py`** - Main startup script (Railway will use this)
✅ **`Procfile`** - Railway process configuration
✅ **`.env.example`** - Environment variable template
✅ **`railway.json`** - Railway configuration (optional)

### Step 2.3: Create/Update Procfile

Create `Procfile` in project root:

```
web: python start.py
```

### Step 2.4: Create railway.json (Optional)

Create `railway.json` for Railway-specific configuration:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Step 2.5: Update .gitignore

Create/update `.gitignore`:

```
# Environment variables
.env

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
ENV/
env/

# Database
*.db
context_memory.db

# Logs
logs/
*.log

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Wake word models (too large for git)
*.ppn
vosk-model*/

# Piper voice models
piper/voices/
```

### Step 2.6: Optimize requirements.txt for Railway

Review `requirements.txt` and ensure it doesn't include local-only dependencies:

**Remove or make optional:**
- `pygame` (only needed for local audio)
- `pyaudio` (only needed for local microphone)
- Large model files (download at runtime if needed)

**Create `requirements-railway.txt`** (leaner version):

```txt
# Web Framework
flask==3.0.0
flask-socketio==5.3.5
python-socketio==5.10.0

# AI/ML
groq==0.4.1
sentence-transformers==2.2.2
torch==2.1.0
tiktoken==0.5.2

# Database
sqlite3  # Built-in with Python

# HTTP
requests==2.31.0
aiohttp==3.9.1

# Environment
python-dotenv==1.0.0

# Utilities
numpy==1.24.3
```

---

## 3. Deploy to Railway

### Step 3.1: Login to Railway

1. Go to https://railway.app
2. Click "Login" and sign in with GitHub
3. Authorize Railway to access your repositories

### Step 3.2: Create New Project

1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your `maxi-ai-robot` repository
4. Railway will auto-detect it's a Python project

### Step 3.3: Configure Build Settings

Railway will automatically:
- ✅ Detect Python project
- ✅ Install dependencies from `requirements.txt`
- ✅ Run `start.py` via Procfile

**If needed, manually configure:**
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python start.py`

### Step 3.4: Wait for Initial Build

Railway will:
1. Clone your repository
2. Install dependencies (~3-5 minutes)
3. Start the application
4. Provide a public URL (e.g., `maxi-ai-robot.railway.app`)

---

## 4. Configure Environment Variables

### Step 4.1: Access Railway Dashboard

1. Click on your deployed project
2. Go to "Variables" tab

### Step 4.2: Add Required Environment Variables

Add these variables one by one:

#### **Core Configuration**
```
PORT=5002
HOST=0.0.0.0
```

#### **LLM Provider (Groq)**
```
LLM_PROVIDER=groq
GROQ_API_KEY=your_actual_groq_api_key_here
```

#### **Speech-to-Text (Groq)**
```
TRANSCRIBER_MODE=groq
```

#### **Parent Dashboard**
```
PARENT_DASHBOARD_PIN=your_secure_pin_here
```

#### **Timeout Configuration**
```
LISTENING_TIMEOUT_ENABLED=true
DEFAULT_LISTENING_TIMEOUT=20.0
SHORT_LISTENING_TIMEOUT=8.0
WAKE_LISTENING_TIMEOUT=45.0
```

#### **Wake Word (Disable for Cloud)**
```
USE_WAKE_WORD=false
```

#### **Audio Mode (Cloud)**
```
AUDIO_MODE=cloud
TTS_ENGINE=cloud
```

#### **Raspberry Pi Connection (Optional)**
```
RASPBERRY_PI_IP=your_pi_public_ip_or_domain
RASPBERRY_PI_PORT=5001
FINGER_SIMULATION_MODE=false
```

### Step 4.3: Save and Redeploy

After adding variables:
1. Click "Save"
2. Railway will automatically redeploy with new variables
3. Wait for deployment to complete (~2-3 minutes)

---

## 5. Connect Raspberry Pi to Railway

### Option A: Public IP with Port Forwarding

#### Step 5.1: Configure Router Port Forwarding

1. Login to your router admin panel
2. Find "Port Forwarding" or "Virtual Server" section
3. Add new rule:
   - **External Port:** 5001
   - **Internal IP:** Your Raspberry Pi's local IP (e.g., 192.168.1.156)
   - **Internal Port:** 5001
   - **Protocol:** TCP
4. Save changes

#### Step 5.2: Get Your Public IP

```bash
# On any computer in your network
curl ifconfig.me
```

#### Step 5.3: Update Railway Environment Variable

```
RASPBERRY_PI_IP=your_public_ip_here
RASPBERRY_PI_PORT=5001
```

---

### Option B: Using Ngrok (Easier, Recommended)

#### Step 5.1: Install Ngrok on Raspberry Pi

```bash
# On Raspberry Pi
cd ~
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz
tar -xvf ngrok-v3-stable-linux-arm.tgz
sudo mv ngrok /usr/local/bin/
```

#### Step 5.2: Sign Up for Ngrok

1. Go to https://ngrok.com
2. Sign up for free account
3. Get your authtoken from dashboard

#### Step 5.3: Configure Ngrok on Pi

```bash
# Authenticate
ngrok config add-authtoken YOUR_NGROK_AUTH_TOKEN

# Start finger controller on Pi (in one terminal)
cd /path/to/your/finger/controller
python3 finger_controller_api.py

# Start ngrok tunnel (in another terminal)
ngrok http 5001
```

#### Step 5.4: Copy Ngrok URL

Ngrok will display:
```
Forwarding: https://abc123.ngrok.io -> http://localhost:5001
```

Copy the `https://abc123.ngrok.io` URL.

#### Step 5.5: Update Railway Environment Variable

```
RASPBERRY_PI_IP=abc123.ngrok.io
RASPBERRY_PI_PORT=443
```

**Note:** Ngrok free tier URL changes each restart. Use paid tier for persistent URLs.

---

### Option C: Cloud Simulation Mode (No Hardware)

If you don't need hardware finger control:

```
FINGER_SIMULATION_MODE=true
RASPBERRY_PI_IP=localhost
RASPBERRY_PI_PORT=5001
```

Railway will run in full simulation mode.

---

## 6. Test the Deployment

### Step 6.1: Access Your Railway URL

Railway provides a public URL like:
```
https://maxi-ai-robot-production.up.railway.app
```

### Step 6.2: Test Core Features

1. **Menu Page:**
   - Visit: `https://your-app.railway.app/`
   - Should see robot face and mode buttons

2. **Chat Mode:**
   - Click "Chat with Maxi"
   - Should enter fullscreen
   - Test voice interaction (if tablet has mic)

3. **Math Mode:**
   - Click "Math & Gestures"
   - Should enter fullscreen
   - Test math questions

4. **Parent Dashboard:**
   - Tap robot face 5 times
   - Enter PIN (default: 1234)
   - Should see all 4 stat cards in one row (landscape)
   - Should have fullscreen prompt

### Step 6.3: Check Logs

In Railway dashboard:
1. Click "Deployments"
2. Select latest deployment
3. Click "View Logs"
4. Look for:
   ```
   ✅ MaxiAI backend thread started
   🧠 Context System: Advanced
   🛡️ Safety Systems: All Active ✓
   ```

### Step 6.4: Test Safety Features

1. Try inappropriate questions (content filter should block)
2. Ask 60+ questions rapidly (rate limiter should warn)
3. Check parent dashboard for logged questions
4. Verify session timer appears after 30 minutes

---

## 7. Troubleshooting

### Issue: "Application Error" on Railway

**Cause:** Missing environment variables or failed build

**Solution:**
```bash
# Check Railway logs
# Common fixes:
1. Verify all environment variables are set
2. Check requirements.txt for missing dependencies
3. Ensure Procfile exists with: web: python start.py
4. Check start.py uses PORT environment variable
```

---

### Issue: Database Errors

**Cause:** SQLite file permissions or missing tables

**Solution:**
Railway automatically creates `context_memory.db` on first run. If issues persist:
- Database migration runs automatically on startup
- Check logs for "🔄 Migrating database schema" message
- No manual intervention needed

---

### Issue: Raspberry Pi Not Connecting

**Cause:** Firewall, port forwarding, or ngrok issues

**Solution:**
```bash
# Test from Railway container (if possible)
curl http://YOUR_PI_IP:5001/health

# Or set simulation mode:
FINGER_SIMULATION_MODE=true
```

---

### Issue: Slow Performance

**Cause:** Railway free tier limitations

**Solutions:**
1. **Upgrade to Hobby Plan ($5/month):**
   - More CPU and RAM
   - Better performance

2. **Optimize Dependencies:**
   - Use lighter models (e.g., smaller sentence-transformers)
   - Remove unnecessary packages

3. **Enable Railway Caching:**
   - Railway caches pip dependencies automatically

---

### Issue: WebSocket Connection Fails

**Cause:** Railway proxy configuration

**Solution:**
Railway supports WebSockets automatically. Ensure:
```python
# In start.py
socketio.run(
    app,
    host='0.0.0.0',
    port=int(os.getenv('PORT', 5002)),
    allow_unsafe_werkzeug=True,
    log_output=True
)
```

---

## 8. Post-Deployment Checklist

### Security

- [ ] Changed `PARENT_DASHBOARD_PIN` from default (1234)
- [ ] Groq API key is kept secure (never commit to git)
- [ ] Raspberry Pi uses HTTPS (ngrok) or is behind firewall
- [ ] Content filter keywords reviewed and customized
- [ ] Rate limiting thresholds configured appropriately

### Monitoring

- [ ] Parent dashboard accessible and showing stats
- [ ] Railway logs show no errors
- [ ] Database tables created successfully
- [ ] All safety systems show "Active ✓"

### Performance

- [ ] App loads within 3 seconds
- [ ] LLM responses appear within 5 seconds
- [ ] No memory leaks in Railway metrics
- [ ] WebSocket connections stable

### Features

- [ ] Chat mode works with voice/text input
- [ ] Math mode processes questions correctly
- [ ] Finger controller responds (or simulation works)
- [ ] Session timer shows break reminders
- [ ] Parent dashboard displays all statistics

### User Experience

- [ ] Fullscreen mode triggers on chat/math/dashboard
- [ ] All 4 stat cards visible in landscape mode
- [ ] Mobile/tablet interface responsive
- [ ] PWA (Progressive Web App) installable

---

## 9. Custom Domain (Optional)

### Step 9.1: Purchase Domain

Buy a domain from:
- Namecheap
- Google Domains
- Cloudflare

### Step 9.2: Configure DNS in Railway

1. Go to Railway project settings
2. Click "Domains"
3. Click "Custom Domain"
4. Enter your domain (e.g., `maxi.yourdomain.com`)
5. Add CNAME record in your DNS provider:
   ```
   CNAME: maxi
   Value: your-app.railway.app
   ```

### Step 9.3: Wait for SSL Certificate

Railway automatically provisions SSL certificate (~5-10 minutes).

---

## 10. Continuous Deployment

Railway automatically redeploys when you push to GitHub:

```bash
# Make changes locally
git add .
git commit -m "Update feature X"
git push origin main

# Railway detects push and redeploys automatically
```

**Deployment Process:**
1. Railway pulls latest code
2. Installs dependencies
3. Runs database migrations (automatic)
4. Starts new instance
5. Routes traffic to new instance
6. Stops old instance

**Zero-downtime deployment!** 🎉

---

## 11. Monitoring & Maintenance

### Railway Dashboard Metrics

Monitor these regularly:
- **CPU Usage:** Should be <50% average
- **Memory Usage:** Should be <512MB
- **Network Traffic:** Varies by usage
- **Build Time:** ~3-5 minutes typical

### Parent Dashboard Analytics

Check weekly:
- Total questions asked
- Learning topics coverage
- Content filter events
- Session duration patterns

### Database Backup

Railway doesn't auto-backup SQLite. Manual backup:

```bash
# Download from Railway deployment
railway run python -c "import shutil; shutil.copy('context_memory.db', 'backup.db')"

# Or use Railway CLI to download logs/files
```

---

## 12. Scaling Considerations

### For High Traffic (100+ concurrent users):

1. **Upgrade Railway Plan:**
   - Pro Plan: $20/month
   - More resources and better performance

2. **Use External Database:**
   - PostgreSQL (Railway provides free tier)
   - Better for concurrent writes

3. **Add Redis for Caching:**
   - Cache LLM responses
   - Reduce database queries

4. **Implement CDN:**
   - Cloudflare for static assets
   - Faster page loads globally

---

## 🎉 Deployment Complete!

Your Maxi AI Robot is now live on Railway with:

✅ Full safety features (content filter, rate limiter, usage tracker)
✅ Parent dashboard with statistics
✅ Automatic database migrations
✅ Raspberry Pi finger control (optional)
✅ Continuous deployment from GitHub
✅ HTTPS and custom domain support
✅ Production-ready configuration

**Your Railway URL:**
```
https://your-app-name.up.railway.app
```

Share with kids and parents! 🚀🤖

---

## Support & Resources

- **Railway Docs:** https://docs.railway.app
- **Groq API Docs:** https://console.groq.com/docs
- **GitHub Repo:** Your repository URL
- **Parent Dashboard:** https://your-app.railway.app/parent-dashboard

---

**Last Updated:** January 16, 2026
**Version:** 2.0 (with Safety Features & Railway Deployment)
