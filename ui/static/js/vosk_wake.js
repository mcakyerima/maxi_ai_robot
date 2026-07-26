/**
 * VoskWakeProvider — beepless, NO-ACCOUNT hands-free wake word for the tablet.
 *
 * Unlike Porcupine (which now needs a verified Picovoice account), Vosk is fully
 * open and keyless. It runs a small offline speech model (WASM, in a worker) over a
 * getUserMedia stream — so, like Porcupine and unlike webkitSpeechRecognition, it
 * listens continuously with NO system beep. We restrict it to a tiny grammar
 * (the wake phrase + "stop") so it stays fast and accurate for keyword spotting.
 *
 * It implements the SAME contract MaxiVoiceEngine expects from a wakeProvider, so
 * it's a drop-in alternative to PorcupineWakeProvider:
 *   isReady() / async init() / async listen() / async pause() / async release()
 *   .onKeyword  (set by the engine; called with the matched phrase)
 *
 * The ~40 MB model is served same-origin from Maxi's own drive (the Railway volume)
 * at window.MAXI_VOICE_CONFIG.voskModelUrl — no runtime CDN, no CORS. The small SDK
 * (vosk.js) loads from a CDN by default (overridable via voskSdkUrl).
 *
 * Defensive throughout: any failure (SDK/model load, mic denied, insecure context)
 * leaves isReady() false and the engine falls back to push-to-talk.
 */
(function (global) {
  "use strict";

  const DEFAULTS = {
    voskSdkUrl: "https://cdn.jsdelivr.net/npm/vosk-browser@0.0.5/dist/vosk.js",
    voskModelUrl: "/models/vosk-model-small-en-us-0.15.tar.gz",
    wakePhrase: "hey maxi",
    extraPhrases: ["stop"], // also spotted (used for beepless barge-in)
  };
  const MODEL_SAMPLE_RATE = 16000;
  const FIRE_COOLDOWN_MS = 1200;

  function log() {
    try { console.log.apply(console, ["[vosk]"].concat([].slice.call(arguments))); } catch (e) {}
  }
  function warn() {
    try { console.warn.apply(console, ["[vosk]"].concat([].slice.call(arguments))); } catch (e) {}
  }

  // Load a classic <script> once and resolve when ready.
  function loadScript(url) {
    return new Promise((resolve, reject) => {
      if (typeof document === "undefined") return reject(new Error("no document"));
      const existing = document.querySelector('script[data-vosk-sdk="1"]');
      if (existing) {
        if (global.Vosk) return resolve();
        existing.addEventListener("load", () => resolve());
        existing.addEventListener("error", () => reject(new Error("vosk sdk load error")));
        return;
      }
      const s = document.createElement("script");
      s.src = url;
      s.async = true;
      s.dataset.voskSdk = "1";
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("failed to load vosk sdk: " + url));
      document.head.appendChild(s);
    });
  }

  class VoskWakeProvider {
    constructor(cfg) {
      const g = (global && global.MAXI_VOICE_CONFIG) || {};
      cfg = Object.assign({}, DEFAULTS, g, cfg || {});
      this.sdkUrl = cfg.voskSdkUrl || DEFAULTS.voskSdkUrl;
      this.modelUrl = cfg.voskModelUrl || DEFAULTS.voskModelUrl;
      this.wakePhrase = (cfg.wakePhrase || DEFAULTS.wakePhrase).toLowerCase();
      const extra = cfg.extraPhrases || DEFAULTS.extraPhrases;
      this._phrases = [this.wakePhrase].concat(extra).map((p) => String(p).toLowerCase());

      this.onKeyword = null; // set by MaxiVoiceEngine

      this._ready = false;
      this._subscribed = false;
      this._initPromise = null;
      this._model = null;
      this._recognizer = null;
      this._media = null;    // MediaStream
      this._audioCtx = null;
      this._source = null;
      this._processor = null;
      this._firedAt = 0;
      this._firedThisUtterance = false;
    }

    configured() { return !!this.modelUrl; }
    isReady() { return this._ready; }

    async init() {
      if (this._ready) return true;
      if (this._initPromise) return this._initPromise;
      this._initPromise = this._init().catch((e) => {
        warn("init failed; hands-free disabled, using fallback:", (e && e.message) || e);
        this._ready = false;
        return false;
      });
      return this._initPromise;
    }

    async _init() {
      if (typeof global.isSecureContext !== "undefined" && !global.isSecureContext) {
        warn("not a secure context (need https/localhost) — mic unavailable.");
        return false;
      }
      log("loading Vosk SDK…");
      await loadScript(this.sdkUrl);
      if (!global.Vosk || !global.Vosk.createModel) {
        throw new Error("Vosk global missing after SDK load");
      }
      log("loading model (served from Maxi's drive):", this.modelUrl, "— first load ~40MB…");
      this._model = await global.Vosk.createModel(this.modelUrl);
      // Restrict recognition to our phrases → fast + accurate keyword spotting.
      const grammar = JSON.stringify(this._phrases.concat(["[unk]"]));
      this._recognizer = new this._model.KaldiRecognizer(MODEL_SAMPLE_RATE, grammar);
      this._recognizer.on("result", (m) => this._onText(m && m.result && m.result.text, true));
      this._recognizer.on("partialresult", (m) => this._onText(m && m.result && m.result.partial, false));

      this._ready = true;
      log("ready — say '" + this.wakePhrase + "' to wake Maxi (no beep).");
      return true;
    }

    // Match the recognizer output against our phrases and fire once per utterance.
    _onText(text, isFinal) {
      if (isFinal) this._firedThisUtterance = false; // new utterance boundary
      if (!text) return;
      const t = String(text).toLowerCase();
      const hit = this._phrases.find((p) => t.indexOf(p) !== -1);
      if (!hit) return;
      const now = Date.now();
      if (this._firedThisUtterance) return;
      if (now - this._firedAt < FIRE_COOLDOWN_MS) return;
      this._firedAt = now;
      this._firedThisUtterance = true;
      log("heard:", JSON.stringify(t), "→ keyword:", hit);
      if (typeof this.onKeyword === "function") this.onKeyword(hit);
    }

    async listen() {
      if (!this._ready || !this._recognizer) return;
      if (this._subscribed) return;
      // Acquire the mic and wire it into the recognizer.
      this._media = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
          sampleRate: MODEL_SAMPLE_RATE,
        },
        video: false,
      });
      const AudioCtx = global.AudioContext || global.webkitAudioContext;
      this._audioCtx = new AudioCtx();
      this._source = this._audioCtx.createMediaStreamSource(this._media);
      this._processor = this._audioCtx.createScriptProcessor(4096, 1, 1);
      this._processor.onaudioprocess = (event) => {
        try {
          if (this._recognizer) this._recognizer.acceptWaveform(event.inputBuffer);
        } catch (e) { /* transient buffer errors are non-fatal */ }
      };
      this._source.connect(this._processor);
      this._processor.connect(this._audioCtx.destination);
      this._subscribed = true;
      this._firedThisUtterance = false;
      log("mic on (listening for wake word)");
    }

    async pause() {
      if (!this._subscribed) return;
      this._teardownAudio();
      this._subscribed = false;
      log("mic released (wake paused)");
    }

    _teardownAudio() {
      try { if (this._processor) { this._processor.disconnect(); this._processor.onaudioprocess = null; } } catch (e) {}
      try { if (this._source) this._source.disconnect(); } catch (e) {}
      try { if (this._audioCtx) this._audioCtx.close(); } catch (e) {}
      try { if (this._media) this._media.getTracks().forEach((tr) => tr.stop()); } catch (e) {}
      this._processor = null;
      this._source = null;
      this._audioCtx = null;
      this._media = null;
    }

    async release() {
      await this.pause();
      try { if (this._recognizer && this._recognizer.remove) this._recognizer.remove(); } catch (e) {}
      try { if (this._model && this._model.terminate) this._model.terminate(); } catch (e) {}
      this._recognizer = null;
      this._model = null;
      this._ready = false;
      this._initPromise = null;
      log("released");
    }
  }

  global.VoskWakeProvider = VoskWakeProvider;
})(typeof window !== "undefined" ? window : this);
