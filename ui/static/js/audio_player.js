/**
 * Cloud Audio Player for Maxi AI
 * Handles audio playback from WebSocket streams
 * Used when backend is deployed to cloud and can't play audio locally
 */

class CloudAudioPlayer {
    constructor() {
        this.audioQueue = [];
        this.isPlaying = false;
        this.audioContext = null;
        this.currentSource = null;
        this.initialized = false;
    }

    /**
     * Initialize Web Audio API
     * Must be called after user interaction due to browser autoplay policies
     */
    async initialize() {
        if (this.initialized) return;
        
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.initialized = true;
            console.log('✅ Audio player initialized');
        } catch (error) {
            console.error('❌ Failed to initialize audio:', error);
            throw error;
        }
    }

    /**
     * Play audio from base64-encoded data
     * @param {string} audioBase64 - Base64-encoded audio data
     * @param {string} format - Audio format (mp3, wav, etc.)
     */
    async playAudio(audioBase64, format = 'mp3') {
        if (!this.initialized) {
            await this.initialize();
        }

        // Add to queue
        this.audioQueue.push({ audioBase64, format });
        
        // Start playing if not already
        if (!this.isPlaying) {
            await this.processQueue();
        }
    }

    /**
     * Process audio queue
     */
    async processQueue() {
        if (this.audioQueue.length === 0) {
            this.isPlaying = false;
            return;
        }

        this.isPlaying = true;
        const { audioBase64, format } = this.audioQueue.shift();

        try {
            // Decode base64 to array buffer
            const binaryString = atob(audioBase64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Decode audio data
            const audioBuffer = await this.audioContext.decodeAudioData(bytes.buffer);

            // Create and play source
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            
            // Wait for playback to complete
            await new Promise((resolve) => {
                source.onended = resolve;
                source.start(0);
            });

            // Process next in queue
            await this.processQueue();

        } catch (error) {
            console.error('❌ Audio playback error:', error);
            // Continue with next audio
            await this.processQueue();
        }
    }

    /**
     * Stop current playback and clear queue
     */
    stop() {
        if (this.currentSource) {
            this.currentSource.stop();
            this.currentSource = null;
        }
        this.audioQueue = [];
        this.isPlaying = false;
    }

    /**
     * Resume audio context (required after browser pause)
     */
    async resume() {
        if (this.audioContext && this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }
    }
}

/**
 * Alternative: Simple HTML5 Audio Player
 * More compatible but less control
 */
class SimpleAudioPlayer {
    constructor() {
        this.audioQueue = [];
        this.isPlaying = false;
        this.audio = new Audio();
        this.onAudioComplete = null; // Callback when all audio finishes
        this.onAudioStart = null; // Callback when audio actually starts playing
        this.onAudioInterrupted = null; // Callback when audio is stopped mid-play
        
        this.audio.addEventListener('ended', () => this.processQueue());
        this.audio.addEventListener('play', () => {
            if (this.onAudioStart && !this.audioStartFired) {
                this.audioStartFired = true;
                this.onAudioStart();
            }
        });
        this.audio.addEventListener('error', (e) => {
            console.error('Audio error:', e);
            this.processQueue(); // Continue with next
        });
        this.audioStartFired = false;
    }

    async initialize() {
        // No initialization needed for HTML5 Audio
        console.log('✅ Simple audio player ready');
    }

    async playAudio(audioBase64, format = 'mp3') {
        this.audioQueue.push({ audioBase64, format });
        
        if (!this.isPlaying) {
            await this.processQueue();
        }
    }

    async processQueue() {
        if (this.audioQueue.length === 0) {
            this.isPlaying = false;
            console.log('🎵 Audio playback complete');
            this.audioStartFired = false;
            // Notify listeners that audio is finished
            if (this.onAudioComplete) {
                this.onAudioComplete();
            }
            return;
        }

        this.isPlaying = true;
        const { audioBase64, format } = this.audioQueue.shift();

        try {
            // Create data URL from base64
            const dataUrl = `data:audio/${format};base64,${audioBase64}`;
            this.audio.src = dataUrl;
            await this.audio.play();
        } catch (error) {
            console.error('❌ Audio playback error:', error);
            await this.processQueue(); // Continue with next
        }
    }

    stop() {
        const wasPlaying = this.isPlaying;
        this.audio.pause();
        this.audio.currentTime = 0;
        this.audioQueue = [];
        this.isPlaying = false;
        this.audioStartFired = false;
        
        // Notify if audio was interrupted
        if (wasPlaying && this.onAudioInterrupted) {
            this.onAudioInterrupted();
        }
    }

    async resume() {
        // Not needed for HTML5 Audio
    }
}

// Export for use in other scripts
window.CloudAudioPlayer = CloudAudioPlayer;
window.SimpleAudioPlayer = SimpleAudioPlayer;
