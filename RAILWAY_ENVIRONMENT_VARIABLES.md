# Railway Environment Variables for Raspberry Pi Integration

This guide explains the environment variables needed to connect Railway to the Raspberry Pi hand controller.

## 📋 Required Variables

### 1. RASPBERRY_PI_URL

**Purpose:** The public URL where the Raspberry Pi finger controller API is accessible.

**Format:** Full URL with protocol (http:// or https://)

**Examples:**
```bash
# ngrok URL (most common)
RASPBERRY_PI_URL=https://abc123xyz.ngrok-free.app

# Custom domain with port forwarding
RASPBERRY_PI_URL=http://my-home-server.ddns.net:5001

# Direct IP with port forwarding (if you have static IP)
RASPBERRY_PI_URL=http://203.0.113.42:5001
```

**Important Notes:**
- ⚠️ **ngrok free tier URLs change on restart** - Update this variable when ngrok restarts
- ✅ Use ngrok paid plan ($8/month) for permanent URL
- ✅ Port 5001 is required (unless you changed it on Pi)
- ❌ Do NOT use localhost or 192.168.x.x (those are local IPs, not accessible from Railway)

---

### 2. MAXI_HAND_API_KEY

**Purpose:** Secure authentication key for Raspberry Pi API requests.

**Format:** Random string (recommend 32-64 characters)

**Generate:**
```bash
# On Mac/Linux/Raspberry Pi
openssl rand -hex 32

# Output example:
# a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
```

**Important Notes:**
- ✅ Must be **exactly the same** on both Railway and Raspberry Pi
- ✅ Use a strong, random key (not a password you use elsewhere)
- ❌ Never commit this key to public repositories
- ✅ Rotate the key periodically for security

---

## 🔧 How to Add Variables to Railway

### Method 1: Railway Dashboard (Recommended)

1. Go to: https://railway.app/project/YOUR_PROJECT_ID
2. Click on your Maxi service
3. Click **"Variables"** tab
4. Click **"+ New Variable"**
5. Add both variables:

```
Variable Name: RASPBERRY_PI_URL
Value: https://abc123xyz.ngrok-free.app
```

```
Variable Name: MAXI_HAND_API_KEY
Value: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
```

6. Railway will **auto-redeploy** after adding variables

### Method 2: Railway CLI

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to project
railway link

# Set variables
railway variables set RASPBERRY_PI_URL=https://abc123xyz.ngrok-free.app
railway variables set MAXI_HAND_API_KEY=your-api-key-here

# Redeploy
railway up
```

---

## 🔄 Updating Variables

### When to Update RASPBERRY_PI_URL

Update this variable when:
- ✅ ngrok restarts (free tier)
- ✅ You switch from ngrok to port forwarding
- ✅ Your public IP changes (if using DDNS)
- ✅ You move the Raspberry Pi to a different network

### How to Update

1. Get new ngrok URL:
   ```bash
   # On Raspberry Pi
   curl http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'
   ```

2. Update Railway variable:
   - Dashboard: Variables tab → Click value → Edit → Save
   - CLI: `railway variables set RASPBERRY_PI_URL=NEW_URL_HERE`

3. Railway will auto-redeploy (takes ~2 minutes)

---

## ✅ Verification

### Check Variables Are Set

```bash
# Railway CLI
railway variables

# Or check in code (Railway logs)
# The finger_controller.py will log:
# "FingerController initialized: https://abc123xyz.ngrok-free.app"
# "🔑 API key authentication enabled"
```

### Test Connection

After deployment, check Railway logs for:
```
✅ Raspberry Pi API is reachable
✅ Finger controller hardware ready!
```

If you see:
```
⚠️ Connection attempt 1 failed: ...
⚠️ Connection attempt 2 failed: ...
⚠️ Connection attempt 3 failed: ...
📡 Falling back to simulation mode (Pi not reachable)
```

Then:
1. Verify `RASPBERRY_PI_URL` is correct and accessible from internet
2. Test URL manually: `curl https://your-pi-url.ngrok-free.app/health`
3. Check `MAXI_HAND_API_KEY` matches on both Pi and Railway
4. Ensure ngrok tunnel is running on Raspberry Pi

---

## 🔐 Security Best Practices

### 1. Protect Your API Key

- ❌ Never commit to Git
- ❌ Never share publicly
- ❌ Never log in production
- ✅ Use Railway's secure variable storage
- ✅ Rotate periodically

### 2. Restrict CORS Origins

The Raspberry Pi API only accepts requests from:
- `https://web-production-0cb67.up.railway.app` (your Railway deployment)
- `http://localhost:5002` (local development)

If your Railway URL changes, update `ALLOWED_ORIGINS` in `finger_controller_api.py`.

### 3. Monitor Access

```bash
# On Raspberry Pi, check for unauthorized access attempts
sudo journalctl -u maxi-hand.service | grep "401"
```

---

## 🚨 Troubleshooting

### "Hardware not available" on Railway

**Check:**
1. Is `RASPBERRY_PI_URL` set correctly?
   ```bash
   railway variables | grep RASPBERRY_PI_URL
   ```

2. Is the URL accessible from internet?
   ```bash
   curl https://your-pi-url.ngrok-free.app/health
   ```

3. Is ngrok running on Pi?
   ```bash
   # On Raspberry Pi
   sudo systemctl status ngrok.service
   ```

### "Authentication failed - check API key"

**Check:**
1. API keys match exactly:
   ```bash
   # Railway
   railway variables | grep MAXI_HAND_API_KEY
   
   # Raspberry Pi
   echo $MAXI_HAND_API_KEY
   ```

2. No extra spaces or quotes in key

3. Key is set on both Pi and Railway

### "CORS error"

**Check:**
1. Railway domain is in `ALLOWED_ORIGINS` on Pi
2. If Railway URL changed, update `finger_controller_api.py`
3. Restart Pi service after changes

---

## 📊 Example Full Configuration

### Raspberry Pi (.env file)
```bash
MAXI_HAND_API_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
ALLOWED_ORIGINS=https://web-production-0cb67.up.railway.app,http://localhost:5002
```

### Railway Variables
```bash
RASPBERRY_PI_URL=https://abc123xyz.ngrok-free.app
MAXI_HAND_API_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
```

**Result:** Railway can securely communicate with Raspberry Pi! 🎉

---

## 🔄 Maintenance

### Weekly Tasks
- [ ] Check ngrok tunnel is running (if using free tier)
- [ ] Verify Railway can connect to Pi
- [ ] Test finger movements from Railway UI

### Monthly Tasks
- [ ] Rotate API key for security
- [ ] Update both Pi and Railway with new key
- [ ] Check for software updates on Pi

### As Needed
- [ ] Update `RASPBERRY_PI_URL` when ngrok restarts
- [ ] Redeploy Railway when environment variables change
- [ ] Monitor Railway logs for connection issues

---

## 📞 Quick Commands Reference

```bash
# Get current Railway variables
railway variables

# Update Pi URL
railway variables set RASPBERRY_PI_URL=NEW_URL

# Test Pi connection from anywhere
curl -H "X-API-Key: YOUR_KEY" https://your-pi-url/health

# Get ngrok URL on Pi
curl http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'

# Restart Pi services
sudo systemctl restart maxi-hand.service
sudo systemctl restart ngrok.service

# Check Railway deployment logs
railway logs
```

---

## ✅ Checklist Before Going Live

- [ ] `RASPBERRY_PI_URL` set correctly on Railway
- [ ] `MAXI_HAND_API_KEY` matches on Pi and Railway
- [ ] ngrok tunnel running and URL is current
- [ ] Pi services auto-start on boot
- [ ] Tested connection from Railway logs
- [ ] Tested finger movement from Railway UI
- [ ] CORS configured for Railway domain
- [ ] API key is strong and secret
- [ ] Monitoring setup (logs, status checks)

---

**You're all set! Maxi can now move its hands from the cloud! 🤖✋**
