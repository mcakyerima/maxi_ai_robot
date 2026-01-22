# Raspberry Pi Hand Controller Setup Guide

Complete guide for setting up Maxi's robotic hands on Raspberry Pi to work with Railway deployment.

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Hardware Setup](#hardware-setup)
3. [Software Installation](#software-installation)
4. [Network Configuration](#network-configuration)
5. [Environment Variables](#environment-variables)
6. [Running the Service](#running-the-service)
7. [Testing Connection](#testing-connection)
8. [Troubleshooting](#troubleshooting)

---

## 🔧 Prerequisites

### Hardware Requirements
- Raspberry Pi 3B+ or newer (4 recommended)
- PCA9685 16-channel PWM servo driver board
- 12 servo motors (6 per hand: thumb, index, middle, ring, pinky, wrist)
- 5V power supply for servos (sufficient amperage for 12 servos)
- I2C connection between Pi and PCA9685

### Software Requirements
- Raspberry Pi OS (Bullseye or newer)
- Python 3.7+
- Internet connection (WiFi or Ethernet)
- SSH access to Raspberry Pi

---

## 🔌 Hardware Setup

### 1. PCA9685 Wiring

Connect the PCA9685 to Raspberry Pi I2C pins:

```
PCA9685         Raspberry Pi
--------        ------------
VCC     →       3.3V (Pin 1)
GND     →       GND (Pin 6)
SDA     →       SDA (Pin 3, GPIO 2)
SCL     →       SCL (Pin 5, GPIO 3)
```

### 2. Servo Channels

Connect servos to PCA9685 channels:

**Left Hand:**
- Channel 0: Thumb
- Channel 1: Index finger
- Channel 2: Middle finger (majeure)
- Channel 3: Ring finger
- Channel 4: Pinky
- Channel 5: Wrist

**Right Hand:**
- Channel 6: Thumb
- Channel 7: Index finger
- Channel 8: Middle finger (majeure)
- Channel 9: Ring finger
- Channel 10: Pinky
- Channel 11: Wrist

### 3. Enable I2C

```bash
sudo raspi-config
# Navigate to: Interface Options → I2C → Enable
# Reboot
sudo reboot
```

Verify I2C is working:
```bash
sudo i2cdetect -y 1
# Should show device at address 0x40 (PCA9685 default)
```

---

## 💻 Software Installation

### 1. Update System

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Install Python Dependencies

```bash
# Install pip if not present
sudo apt install python3-pip -y

# Install required packages
pip3 install Flask==3.0.0
pip3 install Flask-CORS==4.0.0
pip3 install adafruit-circuitpython-pca9685==3.4.0
pip3 install adafruit-blinka==8.20.0
```

### 3. Copy Finger Controller Files

Transfer the updated `finger_controller_api.py` to your Raspberry Pi:

```bash
# From your local machine (where this file is)
scp finger_controller_api.py pi@<PI_IP_ADDRESS>:~/maxi_hand/
scp hand_calibration.json pi@<PI_IP_ADDRESS>:~/maxi_hand/
```

Or manually copy the files via USB, SFTP, or any preferred method.

---

## 🌐 Network Configuration

You need to expose your Raspberry Pi to the internet so Railway can communicate with it. **We recommend ngrok for quick setup**.

### Option A: ngrok (Recommended - Fast & Easy)

#### 1. Install ngrok

```bash
# Download ngrok
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz

# Extract
tar xvzf ngrok-v3-stable-linux-arm.tgz

# Move to system path
sudo mv ngrok /usr/local/bin/

# Verify installation
ngrok version
```

#### 2. Sign Up for ngrok Account

- Go to: https://dashboard.ngrok.com/signup
- Create free account
- Get your authtoken from: https://dashboard.ngrok.com/get-started/your-authtoken

#### 3. Configure ngrok

```bash
# Add your authtoken
ngrok config add-authtoken YOUR_AUTH_TOKEN_HERE
```

#### 4. Start ngrok Tunnel

```bash
# Start tunnel for port 5001
ngrok http 5001
```

You'll see output like:
```
Forwarding    https://abc123xyz.ngrok-free.app -> http://localhost:5001
```

**Copy this URL** - you'll need it for Railway environment variables!

#### 5. Keep ngrok Running (Optional - Auto-Start)

Create a systemd service to auto-start ngrok:

```bash
sudo nano /etc/systemd/system/ngrok.service
```

Add:
```ini
[Unit]
Description=ngrok tunnel
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/local/bin/ngrok http 5001 --log=stdout
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable ngrok.service
sudo systemctl start ngrok.service

# Check status
sudo systemctl status ngrok.service

# View ngrok URL
curl http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'
```

---

### Option B: Port Forwarding (Permanent Solution)

⚠️ **Requires router admin access and either static IP or Dynamic DNS**

#### 1. Configure Static IP on Pi

```bash
sudo nano /etc/dhcpcd.conf
```

Add (adjust for your network):
```
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=8.8.8.8 8.8.4.4
```

#### 2. Router Port Forwarding

- Log into your router admin panel
- Find "Port Forwarding" or "Virtual Server" settings
- Add rule:
  - **External Port:** 5001
  - **Internal IP:** 192.168.1.100 (your Pi's static IP)
  - **Internal Port:** 5001
  - **Protocol:** TCP

#### 3. Get Public IP

```bash
curl ifconfig.me
```

#### 4. Setup Dynamic DNS (if no static IP)

Use services like:
- No-IP (https://www.noip.com/)
- DuckDNS (https://www.duckdns.org/)
- Dynu (https://www.dynu.com/)

Your Railway URL will be: `http://your-ddns-domain.com:5001`

---

## 🔐 Environment Variables

### 1. Generate Secure API Key

```bash
# Generate random 32-character key
openssl rand -hex 32
```

Example output: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6`

**Save this key** - you'll need it for both Pi and Railway!

### 2. Set Environment Variables on Raspberry Pi

```bash
# Create environment file
nano ~/maxi_hand/.env
```

Add:
```bash
MAXI_HAND_API_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
ALLOWED_ORIGINS=https://web-production-0cb67.up.railway.app,http://localhost:5002
```

### 3. Load Environment Variables

```bash
# Add to ~/.bashrc for automatic loading
echo 'export MAXI_HAND_API_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"' >> ~/.bashrc
source ~/.bashrc
```

---

## 🚀 Running the Service

### Manual Start (for testing)

```bash
cd ~/maxi_hand
python3 finger_controller_api.py
```

You should see:
```
🔧 Initializing PCA9685 hardware controller...
✅ PCA9685 initialized at 50Hz
🔒 CORS enabled for origins: ['https://web-production-0cb67.up.railway.app', ...]
🔑 API Key authentication: ENABLED
🚀 Starting Enhanced Maxi AI Finger Controller API
✅ Enhanced Finger Controller API ready!
🌍 Access at: http://0.0.0.0:5001
```

### Auto-Start on Boot (Production)

Create systemd service:

```bash
sudo nano /etc/systemd/system/maxi-hand.service
```

Add:
```ini
[Unit]
Description=Maxi AI Hand Controller API
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/maxi_hand
Environment="MAXI_HAND_API_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"
ExecStart=/usr/bin/python3 /home/pi/maxi_hand/finger_controller_api.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable maxi-hand.service
sudo systemctl start maxi-hand.service

# Check status
sudo systemctl status maxi-hand.service

# View logs
sudo journalctl -u maxi-hand.service -f
```

---

## ✅ Testing Connection

### 1. Local Test (on Raspberry Pi)

```bash
# Test health endpoint (no auth required)
curl http://localhost:5001/health

# Test authenticated endpoint
curl -H "X-API-Key: YOUR_API_KEY_HERE" http://localhost:5001/status
```

### 2. Remote Test (from your computer)

```bash
# Replace with your ngrok URL or public IP
curl https://abc123xyz.ngrok-free.app/health

# Test with authentication
curl -H "X-API-Key: YOUR_API_KEY_HERE" https://abc123xyz.ngrok-free.app/status
```

### 3. Test Finger Movement

```bash
curl -X POST \
  -H "X-API-Key: YOUR_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"hand":"right","number":3}' \
  https://abc123xyz.ngrok-free.app/show_number
```

The right hand should show 3 fingers!

---

## 🔧 Railway Configuration

### Add Environment Variables to Railway

1. Go to Railway dashboard: https://railway.app/project/your-project
2. Click your service → Variables tab
3. Add these variables:

```
RASPBERRY_PI_URL=https://abc123xyz.ngrok-free.app
MAXI_HAND_API_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
```

**Important Notes:**
- `RASPBERRY_PI_URL` is the **ngrok URL** (or your public IP with port)
- `MAXI_HAND_API_KEY` must be **exactly the same** on both Pi and Railway
- If using ngrok free tier, URL changes on restart - update Railway variable each time
- Consider ngrok paid plan ($8/month) for permanent URL

### Redeploy Railway

After adding variables:
1. Click "Deploy" button or push new commit
2. Wait for deployment to complete
3. Test connection from Railway logs

---

## 🐛 Troubleshooting

### Issue: "Authentication failed - check API key"

**Solution:**
1. Verify API key matches on both Pi and Railway
2. Check for extra spaces or line breaks
3. Regenerate key if needed:
   ```bash
   openssl rand -hex 32
   ```

### Issue: "Connection timeout" or "Hardware not available"

**Solution:**
1. Verify ngrok tunnel is running:
   ```bash
   curl http://localhost:4040/api/tunnels
   ```
2. Test local connection first:
   ```bash
   curl http://localhost:5001/health
   ```
3. Check firewall rules:
   ```bash
   sudo ufw status
   # Allow port 5001 if blocked
   sudo ufw allow 5001/tcp
   ```

### Issue: "CORS error" in browser

**Solution:**
1. Verify Railway domain in `ALLOWED_ORIGINS` on Pi
2. Update `finger_controller_api.py` if Railway URL changed
3. Restart Pi service:
   ```bash
   sudo systemctl restart maxi-hand.service
   ```

### Issue: Servos not moving

**Solution:**
1. Check I2C connection:
   ```bash
   sudo i2cdetect -y 1
   # Should show 0x40
   ```
2. Verify power supply to PCA9685 (servos need 5V 2A+)
3. Check servo wiring to correct channels
4. Test emergency stop:
   ```bash
   curl -X POST -H "X-API-Key: YOUR_KEY" \
     http://localhost:5001/reset_emergency
   ```

### Issue: ngrok "session expired"

**Solution:**
- Free ngrok sessions expire after 2 hours of inactivity
- Restart ngrok:
  ```bash
  sudo systemctl restart ngrok.service
  ```
- Get new URL and update Railway:
  ```bash
  curl http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'
  ```

### Issue: Pi loses connection after power outage

**Solution:**
1. Ensure services auto-start:
   ```bash
   sudo systemctl enable maxi-hand.service
   sudo systemctl enable ngrok.service
   ```
2. Add cron job to monitor and restart:
   ```bash
   crontab -e
   # Add:
   */5 * * * * systemctl is-active --quiet maxi-hand.service || systemctl restart maxi-hand.service
   ```

---

## 📊 Monitoring & Logs

### View Service Logs

```bash
# Real-time logs
sudo journalctl -u maxi-hand.service -f

# Last 100 lines
sudo journalctl -u maxi-hand.service -n 100

# ngrok logs
sudo journalctl -u ngrok.service -f
```

### Check Service Status

```bash
# Hand controller
sudo systemctl status maxi-hand.service

# ngrok
sudo systemctl status ngrok.service

# Get ngrok URL
curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'
```

### Monitor System Resources

```bash
# CPU and memory
htop

# Temperature (prevent overheating)
vcgencmd measure_temp

# Disk space
df -h
```

---

## 🔄 Updating the Code

When you update `finger_controller_api.py`:

```bash
# On your computer
scp finger_controller_api.py pi@<PI_IP>:~/maxi_hand/

# On Raspberry Pi
sudo systemctl restart maxi-hand.service

# Verify it's running
sudo systemctl status maxi-hand.service
```

---

## 🎯 Quick Start Checklist

- [ ] Hardware connected (PCA9685 + servos)
- [ ] I2C enabled and verified
- [ ] Python dependencies installed
- [ ] `finger_controller_api.py` copied to Pi
- [ ] API key generated and set
- [ ] ngrok installed and configured
- [ ] ngrok tunnel started
- [ ] ngrok URL copied
- [ ] Railway environment variables updated
- [ ] `maxi-hand.service` created and started
- [ ] Local test passed (curl)
- [ ] Remote test passed (from internet)
- [ ] Finger movement test passed
- [ ] Railway deployment updated
- [ ] End-to-end test from Railway successful

---

## 📞 Support

If you encounter issues not covered here:

1. Check Railway logs for connection errors
2. Check Pi logs: `sudo journalctl -u maxi-hand.service -f`
3. Verify ngrok is running and URL is current
4. Test local connection before troubleshooting remote
5. Ensure API keys match exactly

---

## 🎉 Success!

If you can see finger movements from Railway, congratulations! Maxi's hands are now connected to the cloud! 🤖✋

Try asking Maxi: **"What is 2 plus 3?"** and watch the fingers count!
