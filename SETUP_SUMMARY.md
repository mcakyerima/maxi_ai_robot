# 🤖 Maxi's Hands - Railway Integration Quick Start

## ✅ What We've Done

Successfully integrated Raspberry Pi hand controller with Railway deployment! Here's what was implemented:

### 🔐 Security Enhancements
- **API Key Authentication**: All Pi endpoints now require `X-API-Key` header
- **CORS Protection**: Only Railway domain can access Pi API
- **Environment Variables**: Secure configuration without hardcoding

### 🔄 Connection Reliability
- **Retry Logic**: 3 attempts with exponential backoff (1s, 2s, 5s)
- **Graceful Degradation**: Falls back to simulation mode if Pi is offline
- **Health Checks**: Continuous monitoring of Pi connection status
- **Auto-Reconnect**: Attempts to reconnect on every API call

### 📚 Documentation
- **RASPBERRY_PI_SETUP.md**: Complete Pi setup guide (hardware, software, networking)
- **RAILWAY_ENVIRONMENT_VARIABLES.md**: Environment variable configuration guide
- **requirements_pi.txt**: Pi-specific Python dependencies

---

## 🚀 Next Steps (For You)

### 1. Setup Raspberry Pi (30-45 minutes)

Follow the comprehensive guide in [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md):

1. **Hardware Setup**
   - Connect PCA9685 to Pi I2C pins
   - Wire 12 servos to channels 0-11
   - Enable I2C interface

2. **Software Installation**
   ```bash
   pip3 install -r requirements_pi.txt
   ```

3. **Copy Updated Files**
   - Transfer `finger_controller_api.py` to Pi
   - Copy `hand_calibration.json` if you have it

4. **Generate API Key**
   ```bash
   openssl rand -hex 32
   ```
   Save this key - you'll need it for both Pi and Railway!

5. **Setup ngrok (Recommended)**
   ```bash
   # Install
   wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz
   tar xvzf ngrok-v3-stable-linux-arm.tgz
   sudo mv ngrok /usr/local/bin/
   
   # Configure
   ngrok config add-authtoken YOUR_TOKEN_FROM_NGROK_DASHBOARD
   
   # Start tunnel
   ngrok http 5001
   ```
   
   **Copy the ngrok URL** (e.g., `https://abc123xyz.ngrok-free.app`)

6. **Set Environment Variables on Pi**
   ```bash
   export MAXI_HAND_API_KEY="your-generated-key-here"
   ```

7. **Start Service**
   ```bash
   python3 finger_controller_api.py
   ```

### 2. Configure Railway (5 minutes)

Follow the guide in [RAILWAY_ENVIRONMENT_VARIABLES.md](RAILWAY_ENVIRONMENT_VARIABLES.md):

1. Go to Railway Dashboard → Your Project → Variables
2. Add two variables:
   ```
   RASPBERRY_PI_URL=https://abc123xyz.ngrok-free.app
   MAXI_HAND_API_KEY=your-generated-key-here
   ```
3. Railway will auto-redeploy (takes ~2 minutes)

### 3. Test Everything (10 minutes)

1. **Test Local Connection** (on Pi):
   ```bash
   curl http://localhost:5001/health
   ```

2. **Test Remote Connection** (from your computer):
   ```bash
   curl https://abc123xyz.ngrok-free.app/health
   ```

3. **Test Authenticated Request**:
   ```bash
   curl -H "X-API-Key: YOUR_KEY" https://abc123xyz.ngrok-free.app/status
   ```

4. **Test Finger Movement**:
   ```bash
   curl -X POST \
     -H "X-API-Key: YOUR_KEY" \
     -H "Content-Type: application/json" \
     -d '{"hand":"right","number":3}' \
     https://abc123xyz.ngrok-free.app/show_number
   ```

5. **Test from Railway UI**:
   - Go to: https://web-production-0cb67.up.railway.app
   - Ask Maxi: "What is 2 plus 3?"
   - Watch the hands count! 🎉

---

## 📋 File Changes Summary

### Updated Files

1. **finger_controller_api.py** (Raspberry Pi)
   - Added Flask-CORS for Railway domain
   - Added API key authentication decorator
   - Applied `@require_api_key` to all endpoints
   - Added environment variable support
   - Protected all 16 endpoints with authentication

2. **brain/controller/finger_controller.py** (Railway)
   - Added retry logic with exponential backoff
   - Added API key header support
   - Enhanced connection initialization
   - Added health monitoring
   - Improved error handling and logging

### New Files

3. **RASPBERRY_PI_SETUP.md**
   - Complete hardware setup guide
   - Software installation steps
   - ngrok configuration
   - Service auto-start setup
   - Troubleshooting guide

4. **RAILWAY_ENVIRONMENT_VARIABLES.md**
   - Environment variable documentation
   - Configuration examples
   - Security best practices
   - Troubleshooting guide

5. **requirements_pi.txt**
   - Pi-specific dependencies
   - Flask, Flask-CORS
   - Adafruit PCA9685 libraries

---

## 🔧 Railway Environment Variables

**You MUST add these to Railway:**

```bash
RASPBERRY_PI_URL=https://your-ngrok-url.ngrok-free.app
MAXI_HAND_API_KEY=your-32-character-api-key-here
```

### How to Get These Values:

1. **RASPBERRY_PI_URL**: 
   - From ngrok output after running `ngrok http 5001`
   - Or from: `curl http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'`

2. **MAXI_HAND_API_KEY**:
   - Generate: `openssl rand -hex 32`
   - Use the same key on both Pi and Railway!

---

## 🎯 Architecture Overview

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Railway       │         │      ngrok       │         │  Raspberry Pi   │
│   (Maxi AI)     │────────>│   Tunnel/Proxy   │────────>│  (Hand API)     │
│                 │  HTTPS  │                  │  HTTP   │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                                                   │
                                                                   v
                                                          ┌─────────────────┐
                                                          │    PCA9685      │
                                                          │  PWM Controller │
                                                          └─────────────────┘
                                                                   │
                                                                   v
                                                          ┌─────────────────┐
                                                          │   12 Servos     │
                                                          │  (Hand Fingers) │
                                                          └─────────────────┘

Flow:
1. User asks math question on Railway UI
2. Maxi's brain detects math and calculates answer
3. Railway sends authenticated request to ngrok URL
4. ngrok forwards to local Pi (port 5001)
5. Pi API validates API key
6. Pi moves servo motors to show number
7. Fingers display the answer! ✋
```

---

## 🔐 Security Features

- ✅ API key authentication (prevents unauthorized access)
- ✅ CORS restrictions (only Railway domain allowed)
- ✅ No hardcoded credentials
- ✅ Environment variable configuration
- ✅ Secure key generation (32-byte random)
- ✅ 401 Unauthorized on invalid key
- ✅ Request logging for monitoring

---

## 🐛 Common Issues & Solutions

### Issue: Railway can't connect to Pi

**Solutions:**
1. Verify ngrok is running: `sudo systemctl status ngrok.service`
2. Check Railway variables are set correctly
3. Test ngrok URL manually: `curl https://your-ngrok-url/health`
4. Check Pi service: `sudo systemctl status maxi-hand.service`

### Issue: "Authentication failed"

**Solutions:**
1. API keys must match exactly on Pi and Railway
2. No spaces or quotes around the key
3. Regenerate key if needed: `openssl rand -hex 32`

### Issue: ngrok URL expired

**Solutions:**
- Free ngrok sessions change on restart
- Get new URL: `curl http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'`
- Update Railway variable
- Consider ngrok paid plan ($8/month) for permanent URL

---

## 📊 Expected Log Output

### Railway Logs (Success):
```
FingerController initialized: https://abc123xyz.ngrok-free.app
🔑 API key authentication enabled
Connecting to finger controller at https://abc123xyz.ngrok-free.app (attempt 1/3)...
✅ Raspberry Pi API is reachable
✅ Finger controller hardware ready!
```

### Railway Logs (Pi Offline):
```
Connection attempt 1 failed: ...
Retrying in 1 seconds...
Connection attempt 2 failed: ...
Retrying in 2 seconds...
Connection attempt 3 failed: ...
📡 Falling back to simulation mode (Pi not reachable)
```

### Pi Logs (Success):
```
🔧 Initializing PCA9685 hardware controller...
✅ PCA9685 initialized at 50Hz
🔒 CORS enabled for origins: ['https://web-production-0cb67.up.railway.app', ...]
🔑 API Key authentication: ENABLED
✅ Enhanced Finger Controller API ready!
🌍 Access at: http://0.0.0.0:5001
```

---

## ✅ Success Checklist

Before testing end-to-end:

- [ ] Pi hardware connected and I2C working
- [ ] `finger_controller_api.py` running on Pi
- [ ] ngrok tunnel running and URL obtained
- [ ] API key generated and set on Pi
- [ ] Railway variables configured
- [ ] Railway deployment completed
- [ ] Local Pi test passed
- [ ] Remote Pi test passed
- [ ] Authenticated request test passed
- [ ] Finger movement test passed

---

## 🎉 Final Test

Once everything is set up:

1. Go to: https://web-production-0cb67.up.railway.app
2. Click the microphone button
3. Say: **"Hey Maxi, what is 2 plus 3?"**
4. Watch Maxi:
   - Answer verbally: "2 plus 3 equals 5"
   - Show on screen: The calculation
   - **Move fingers**: Right hand shows 5 fingers! ✋

**If the fingers move, you did it! Maxi's brain is connected to its body! 🤖🎊**

---

## 📚 Documentation Reference

- **Full Pi Setup**: [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md)
- **Environment Variables**: [RAILWAY_ENVIRONMENT_VARIABLES.md](RAILWAY_ENVIRONMENT_VARIABLES.md)
- **Pi Dependencies**: [requirements_pi.txt](requirements_pi.txt)

---

## 🔄 Deployment Status

✅ **Code Changes**: Committed and pushed to Railway
✅ **Railway**: Auto-deploying now
⏳ **Raspberry Pi**: Waiting for your setup
⏳ **Testing**: Ready after Pi is configured

---

## 💡 Tips

1. **Start with ngrok** - It's the fastest way to get started (5 minutes)
2. **Test locally first** - Always verify Pi works before testing from Railway
3. **Keep ngrok running** - Consider setting up systemd service for auto-start
4. **Monitor logs** - Use `sudo journalctl -u maxi-hand.service -f` on Pi
5. **Save your API key** - You'll need it if you restart services

---

## 📞 Need Help?

Check the troubleshooting sections in:
- [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md#troubleshooting)
- [RAILWAY_ENVIRONMENT_VARIABLES.md](RAILWAY_ENVIRONMENT_VARIABLES.md#troubleshooting)

Or verify:
1. ngrok tunnel is active
2. API keys match exactly
3. Railway variables are set
4. Pi service is running
5. Firewall allows port 5001

---

**Ready to bring Maxi's hands to life? Follow the setup guides and let's test it! 🚀**
