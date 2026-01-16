/**
 * Kiosk Mode Enforcer
 * Forces fullscreen, blocks exits, and prevents unauthorized interactions
 */

class KioskMode {
    constructor() {
        this.isKiosk = true;
        this.init();
    }

    init() {
        this.enforceFullscreen();
        this.blockExitShortcuts();
        this.blockContextMenu();
        this.blockPhysicalButtons();
        this.blockSwipeGestures();
        this.lockOrientation();
        this.startFullscreenMonitor();
    }

    enforceFullscreen() {
        const requestFullscreen = 
            document.documentElement.requestFullscreen ||
            document.documentElement.webkitRequestFullscreen || 
            document.documentElement.mozRequestFullScreen ||
            document.documentElement.msRequestFullscreen;

        if (requestFullscreen) {
            requestFullscreen.call(document.documentElement).catch(err => {
                console.error('Fullscreen error:', err);
            });
        }
    }

    blockExitShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Block Escape, Ctrl+F, F11
            if (e.key === 'Escape' || 
                (e.ctrlKey && e.key === 'f') || 
                (e.ctrlKey && e.key === 'F') ||
                e.key === 'F11') {
                e.preventDefault();
                this.enforceFullscreen();
            }
        });
    }

    blockContextMenu() {
        document.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            return false;
        });
    }

    blockPhysicalButtons() {
        document.addEventListener('keydown', (e) => {
            // Block Backspace, Volume, Power buttons
            if (['Backspace', 'VolumeDown', 'VolumeUp', 'Power'].includes(e.key)) {
                e.preventDefault();
            }
        });
    }

    blockSwipeGestures() {
        let touchStartX = 0;
        
        document.addEventListener('touchstart', (e) => {
            touchStartX = e.changedTouches[0].screenX;
        }, {passive: false});

        // document.addEventListener('touchmove', (e) => {
        //     if (Math.abs(e.changedTouches[0].screenX - touchStartX) > 50) {
        //         e.preventDefault();
        //     }
        // }, {passive: false});

        window.addEventListener('touchmove', function(e) {
            if (!e.target.closest('.math-display')) {
                e.preventDefault(); // block scroll elsewhere
            }
        }, { passive: false });

        }

    lockOrientation() {
        if (screen.orientation?.lock) {
            screen.orientation.lock('landscape').catch(() => {});
        } else if (window.screen.lockOrientation) {
            window.screen.lockOrientation('landscape');
        }
    }

    startFullscreenMonitor() {
        setInterval(() => {
            if (!document.fullscreenElement && !document.webkitFullscreenElement) {
                this.enforceFullscreen();
            }
        }, 30000);

        document.addEventListener('fullscreenchange', () => {
            if (!document.fullscreenElement) {
                this.enforceFullscreen();
            }
        });
    }
}

// Auto-initialize when imported
const kiosk = new KioskMode();

// Export for manual control if needed
export default kiosk;