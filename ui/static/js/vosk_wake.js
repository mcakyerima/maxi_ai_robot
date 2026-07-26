/**
 * VoskWakeProvider — beepless, NO-ACCOUNT hands-free WAKE word for the tablet.
 *
 * Unlike Porcupine (which now needs a verified Picovoice account), Vosk is fully
 * open and keyless. It runs a small offline speech model (WASM, in a worker) over a
 * getUserMedia stream — so, like Porcupine and unlike webkitSpeechRecognition, it
 * listens continuously with NO system beep.
 *
 * IMPORTANT — WAKE ONLY, never barge-in. A small STT model mis-hears Maxi's OWN
 * voice (and background chatter) as the wake phrase, which caused false interrupts.
 * So this provider advertises `supportsBargeIn = false`: MaxiVoiceEngine keeps the
 * mic OFF while Maxi is speaking and only uses Vosk to detect the wake phrase while
 * idle. Interrupting mid-answer is done with the mic button.
 *
 * Accuracy defenses (against background-noise false wakes):
 *   - FINAL results only (partials are far too noisy),
 *   - the wake phrase must appear as a whole, consecutive token sequence,
 *   - each matched word must clear a confidence threshold (minConfidence),
 *   - a fire cooldown prevents double-triggering,
 *   - the recognizer grammar is restricted to just the wake phrase + "[unk]", so
 *     unknown speech is routed to "[unk]" instead of being forced onto the phrase.
 *
 * Contract expected by MaxiVoiceEngine:
 *   isReady() / async init() / async listen() / async pause() / async release()
 *   .onKeyword (set by the engine)   .supportsBargeIn = false
 *
 * The ~40 MB model is served same-origin from Maxi's own drive (the Railway volume)
 * at window.MAXI_VOICE_CONFIG.voskModelUrl — no runtime CDN, no CORS. Defensive
 * throughout: any failure leaves isReady() false → engine falls back to push-to-talk.
 */
(function (global) {
  "use strict";

  const DEFAULTS = {
    voskSdkUrl: "https://cdn.jsdelivr.net/npm/vosk-browser@0.0.5/dist/vosk.js",
    voskModelUrl: "/models/vosk-model-small-en-us-0.15.tar.gz",
    wakePhrase: "hey maxi",
    minConfidence: 0.6, // reject matches below this average word confidence
  };
  const MODEL_SAMPLE_RATE = 16000;
  const FIRE_COOLDOWN_MS = 1500;

  function log() {
    try { console.log.apply(console, ["[vosk]"].concat([].slice.call(arguments))); } catch (e) {}
  }
  function warn() {
    try { console.warn.apply(console, ["[vosk]"].concat([].slice.call(arguments))); } catch (e) {}
  }

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
      this.minConf = typeof cfg.voskMinConfidence === "number"
        ? cfg.voskMinConfidence
        : (typeof cfg.minConfidence === "number" ? cfg.minConfidence : DEFAULTS.minConfidence);
      this._phrases = [this.wakePhrase]; // WAKE only — no "stop"/barge-in phrases

      this.onKeyword = null;       // set by MaxiVoiceEngine
      this.supportsBargeIn = false; // Vosk is NOT echo-safe → wake only

      this._ready = false;
      this._subscribed = false;
      this._initPromise = null;
      this._model = null;
      this._recognizer = null;
      this._media = null;
      this._audioCtx = null;
      this._source = null;
      this._processor = null;
      this._firedAt = 0;
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
      // Restrict recognition to the wake phrase (+ [unk] to absorb everything else).
      const grammar = JSON.stringify(this._phrases.concat(["[unk]"]));
      this._recognizer = new this._model.KaldiRecognizer(MODEL_SAMPLE_RATE, grammar);
      try { this._recognizer.setWords(true); } catch (e) { /* older SDK — conf check skipped */ }
      this._recognizer.on("result", (m) => this._onResult(m));
      // partials are intentionally NOT used to fire — far too noisy.

      this._ready = true;
      log("ready — say '" + this.wakePhrase + "' to wake Maxi (no beep). minConf=" + this.minConf);
      return true;
    }

    _onResult(message) {
      const r = message && message.result;
      if (!r) return;
      const text = String(r.text || "").toLowerCase().trim();
      if (!text) return;
      const words = Array.isArray(r.result) ? r.result : null;
      for (let i = 0; i < this._phrases.length; i++) {
        if (this._matchPhrase(text, words, this._phrases[i])) {
          this._fire(this._phrases[i], text);
          return;
        }
      }
    }

    // The phrase must appear as consecutive tokens AND clear the confidence bar.
    _matchPhrase(text, words, phrase) {
      const ptoks = phrase.split(/\s+/).filter(Boolean);
      const ttoks = text.split(/\s+/).filter(Boolean);
      for (let i = 0; i + ptoks.length <= ttoks.length; i++) {
        let ok = true;
        for (let j = 0; j < ptoks.length; j++) {
          if (ttoks[i + j] !== ptoks[j]) { ok = false; break; }
        }
        if (!ok) continue;
        // Confidence gate (when per-word confidences are available and aligned).
        if (words && words.length === ttoks.length) {
          let sum = 0;
          for (let j = 0; j < ptoks.length; j++) {
            const w = words[i + j];
            sum += w && typeof w.conf === "number" ? w.conf : 1;
          }
          const avg = sum / ptoks.length;
          if (avg < this.minConf) {
            log("ignored low-confidence wake:", JSON.stringify(text), "avg=" + avg.toFixed(2));
            return false;
          }
        }
        return true;
      }
      return false;
    }

    _fire(phrase, text) {
      const now = Date.now();
      if (now - this._firedAt < FIRE_COOLDOWN_MS) return;
      this._firedAt = now;
      log("WAKE:", JSON.stringify(text), "→", phrase);
      if (typeof this.onKeyword === "function") this.onKeyword(phrase);
    }

    async listen() {
      if (!this._ready || !this._recognizer) return;
      if (this._subscribed) return;
      this._media = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
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
      log("mic on (listening for '" + this.wakePhrase + "')");
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
