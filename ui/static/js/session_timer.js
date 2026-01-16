/**
 * Session Timer for Maxi AI - Parental Controls
 * Tracks session duration and provides gentle break reminders
 */

class SessionTimer {
    constructor() {
        this.startTime = Date.now();
        this.duration = 0; // in seconds
        this.breakReminders = {
            30: false,  // 30 minutes
            45: false,  // 45 minutes
            60: false   // 60 minutes
        };
        this.timerInterval = null;
        this.progressBar = null;
        this.timeDisplay = null;
        
        this.init();
    }
    
    init() {
        this.createUI();
        this.start();
    }
    
    createUI() {
        // Create timer container
        const timerContainer = document.createElement('div');
        timerContainer.id = 'session-timer';
        timerContainer.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: rgba(0, 0, 0, 0.2);
            z-index: 9998;
            display: flex;
            align-items: center;
        `;
        
        // Progress bar
        this.progressBar = document.createElement('div');
        this.progressBar.style.cssText = `
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #11998e 0%, #38ef7d 100%);
            transition: width 1s linear, background 0.3s ease;
        `;
        
        // Time display (hidden by default, shows on hover)
        this.timeDisplay = document.createElement('div');
        this.timeDisplay.style.cssText = `
            position: absolute;
            right: 10px;
            top: 6px;
            background: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 5px 10px;
            border-radius: 10px;
            font-size: 0.8rem;
            font-weight: 600;
            opacity: 0;
            transition: opacity 0.3s ease;
            pointer-events: none;
        `;
        
        timerContainer.appendChild(this.progressBar);
        timerContainer.appendChild(this.timeDisplay);
        document.body.appendChild(timerContainer);
        
        // Show time display on hover
        timerContainer.addEventListener('mouseenter', () => {
            this.timeDisplay.style.opacity = '1';
        });
        timerContainer.addEventListener('mouseleave', () => {
            this.timeDisplay.style.opacity = '0';
        });
    }
    
    start() {
        this.timerInterval = setInterval(() => {
            this.duration = Math.floor((Date.now() - this.startTime) / 1000);
            this.update();
            this.checkBreakReminders();
        }, 1000);
    }
    
    update() {
        const minutes = Math.floor(this.duration / 60);
        const seconds = this.duration % 60;
        
        // Update time display
        this.timeDisplay.textContent = `Learning Time: ${minutes}m ${seconds}s`;
        
        // Update progress bar (max 60 minutes = 100%)
        const progressPercent = Math.min((this.duration / 3600) * 100, 100);
        this.progressBar.style.width = `${progressPercent}%`;
        
        // Change color based on duration
        if (minutes >= 60) {
            this.progressBar.style.background = 'linear-gradient(90deg, #f093fb 0%, #f5576c 100%)'; // Warning red
        } else if (minutes >= 45) {
            this.progressBar.style.background = 'linear-gradient(90deg, #f093fb 0%, #f5576c 60%)'; // Orange
        } else if (minutes >= 30) {
            this.progressBar.style.background = 'linear-gradient(90deg, #11998e 0%, #f5576c 100%)'; // Yellow-green
        }
    }
    
    checkBreakReminders() {
        const minutes = Math.floor(this.duration / 60);
        
        // 30 minute reminder
        if (minutes >= 30 && !this.breakReminders[30]) {
            this.breakReminders[30] = true;
            this.showBreakReminder(
                "Great job learning! 🌟",
                "You've been learning for 30 minutes. Maybe take a quick 5-minute break?"
            );
        }
        
        // 45 minute reminder
        if (minutes >= 45 && !this.breakReminders[45]) {
            this.breakReminders[45] = true;
            this.showBreakReminder(
                "You're doing amazing! 🎉",
                "45 minutes of learning! Time to rest your eyes and stretch!"
            );
        }
        
        // 60 minute reminder (stronger)
        if (minutes >= 60 && !this.breakReminders[60]) {
            this.breakReminders[60] = true;
            this.showBreakReminder(
                "Wow, a whole hour! 🏆",
                "Let's take a real break now. Come back soon, superstar!",
                true // More prominent
            );
        }
    }
    
    showBreakReminder(title, message, important = false) {
        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, ${important ? '0.8' : '0.6'});
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.3s ease;
        `;
        
        // Create reminder card
        const card = document.createElement('div');
        card.style.cssText = `
            background: linear-gradient(145deg, #667eea 0%, #764ba2 100%);
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 30px;
            padding: 40px;
            max-width: 500px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            animation: slideIn 0.4s ease;
        `;
        
        card.innerHTML = `
            <h2 style="
                font-family: 'Fredoka One', cursive;
                font-size: 2.5rem;
                color: white;
                margin-bottom: 20px;
            ">${title}</h2>
            <p style="
                font-family: 'Nunito', sans-serif;
                font-size: 1.3rem;
                color: rgba(255, 255, 255, 0.9);
                margin-bottom: 30px;
                line-height: 1.6;
            ">${message}</p>
            <button id="continue-btn" style="
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                border: none;
                border-radius: 15px;
                padding: 15px 40px;
                font-size: 1.2rem;
                font-weight: 700;
                color: white;
                cursor: pointer;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            ">
                ${important ? "I'll Take a Break!" : "Continue Learning"}
            </button>
        `;
        
        overlay.appendChild(card);
        document.body.appendChild(overlay);
        
        // Button hover effect
        const btn = document.getElementById('continue-btn');
        btn.addEventListener('mouseenter', () => {
            btn.style.transform = 'translateY(-2px)';
            btn.style.boxShadow = '0 6px 20px rgba(0, 0, 0, 0.4)';
        });
        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'translateY(0)';
            btn.style.boxShadow = '0 4px 15px rgba(0, 0, 0, 0.3)';
        });
        
        // Close on button click
        btn.addEventListener('click', () => {
            overlay.style.animation = 'fadeOut 0.3s ease';
            setTimeout(() => overlay.remove(), 300);
        });
        
        // Add animations
        const style = document.createElement('style');
        style.textContent = `
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes fadeOut {
                from { opacity: 1; }
                to { opacity: 0; }
            }
            @keyframes slideIn {
                from { transform: translateY(-50px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    }
    
    getStats() {
        const minutes = Math.floor(this.duration / 60);
        const seconds = this.duration % 60;
        
        return {
            duration_seconds: this.duration,
            duration_minutes: minutes,
            formatted: `${minutes}m ${seconds}s`,
            break_reminders_shown: Object.values(this.breakReminders).filter(Boolean).length
        };
    }
    
    reset() {
        this.startTime = Date.now();
        this.duration = 0;
        this.breakReminders = {30: false, 45: false, 60: false};
        this.update();
    }
    
    stop() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }
}

// Auto-initialize when script loads
let sessionTimer = null;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        sessionTimer = new SessionTimer();
        console.log('📊 Session timer initialized');
    });
} else {
    sessionTimer = new SessionTimer();
    console.log('📊 Session timer initialized');
}

// Export for external access
window.SessionTimer = SessionTimer;
window.sessionTimer = sessionTimer;
