/**
 * PorcupineWakeProvider — beepless on-device wake-word detection for the tablet.
 *
 * This is the real hands-free "Hey Maxi" engine. It runs Picovoice Porcupine
 * (WebAssembly) over a getUserMedia stream via WebVoiceProcessor, so — unlike
 * Android's webkitSpeechRecognition — it listens continuously with NO system beep.
 * MaxiVoiceEngine plugs it in as `wakeProvider`: it powers the idle WAKE stage and
 * the speaking BARGE_IN stage; the engine still uses webkitSpeechRecognition for the
 * one-shot question capture (one acceptable beep per question).
 *
 * Contract expected by MaxiVoiceEngine:
 *   isReady()        -> bool          (SDK loaded + worker created)
 *   async init()     -> bool          (load SDK from CDN + create the worker)
 *   async listen()   -> subscribe the mic (idempotent)
 *   async pause()    -> release the mic (idempotent) so CAPTURE can use it
 *   async release()  -> full teardown
 *   .onKeyword       -> set by the engine; called with the detected keyword label
 *
 * Everything is defensive: if the AccessKey is missing or the CDN import/create
 * fails, isReady() stays false and the engine silently falls back to its existing
 * push-to-talk behavior. Hands-free is a progressive enhancement, never a hard dep.
 *
 * Config comes from window.MAXI_VOICE_CONFIG (served by /voice_config.js), or can be
 * passed directly to the constructor. Keys:
 *   picovoiceAccessKey (required)   keyword ("Computer" | ... built-in)
 *   keywordUrl (optional custom .ppn, e.g. a trained "Hey Maxi")
 *   keywordLabel (label for the custom .ppn)   sensitivity (0..1)
 *   modelUrl (porcupine_params.pv)  sdkPorcupineUrl / sdkVpUrl (ESM module URLs)
 */
(function (global) {
  "use strict";

  const JSDELIVR = "https://cdn.jsdelivr.net";
  const DEFAULTS = {
    keyword: "Computer",
    sensitivity: 0.6,
    keywordUrl: "",
    keywordLabel: "Hey Maxi",
    // The Porcupine acoustic model (~4 MB). Overridable / vendorable.
    modelUrl: JSDELIVR + "/gh/Picovoice/porcupine@master/lib/common/porcupine_params.pv",
    // ESM builds (jsDelivr bundles deps with the /+esm suffix).
    sdkPorcupineUrl: JSDELIVR + "/npm/@picovoice/porcupine-web@3.0.3/+esm",
    sdkVpUrl: JSDELIVR + "/npm/@picovoice/web-voice-processor@4.0.9/+esm",
  };

  function log() {
    try { console.log.apply(console, ["[wake]"].concat([].slice.call(arguments))); } catch (e) {}
  }
  function warn() {
    try { console.warn.apply(console, ["[wake]"].concat([].slice.call(arguments))); } catch (e) {}
  }

  class PorcupineWakeProvider {
    constructor(cfg) {
      const g = (global && global.MAXI_VOICE_CONFIG) || {};
      cfg = Object.assign({}, DEFAULTS, g, cfg || {});
      this.accessKey = cfg.picovoiceAccessKey || cfg.accessKey || "";
      this.keyword = cfg.keyword || DEFAULTS.keyword;
      this.sensitivity = typeof cfg.sensitivity === "number" ? cfg.sensitivity : DEFAULTS.sensitivity;
      this.keywordUrl = cfg.keywordUrl || "";
      this.keywordLabel = cfg.keywordLabel || DEFAULTS.keywordLabel;
      this.modelUrl = cfg.modelUrl || DEFAULTS.modelUrl;
      this.sdkPorcupineUrl = cfg.sdkPorcupineUrl || DEFAULTS.sdkPorcupineUrl;
      this.sdkVpUrl = cfg.sdkVpUrl || DEFAULTS.sdkVpUrl;

      this.onKeyword = null; // set by MaxiVoiceEngine

      this._ready = false;
      this._subscribed = false;
      this._initPromise = null;
      this._worker = null;
      this._vp = null; // WebVoiceProcessor class
    }

    configured() {
      return !!this.accessKey;
    }
    isReady() {
      return this._ready;
    }

    // Load the SDK from CDN and create the Porcupine worker. Idempotent; returns
    // true on success. Never throws — resolves false and stays not-ready on failure.
    async init() {
      if (this._ready) return true;
      if (this._initPromise) return this._initPromise;
      this._initPromise = this._init().catch((e) => {
        warn("init failed; hands-free disabled, using fallback:", e && e.message || e);
        this._ready = false;
        return false;
      });
      return this._initPromise;
    }

    async _init() {
      if (!this.configured()) {
        log("no Picovoice AccessKey — hands-free off (set PICOVOICE_ACCESS_KEY).");
        return false;
      }
      if (typeof global.isSecureContext !== "undefined" && !global.isSecureContext) {
        warn("not a secure context (need https/localhost) — mic + wake word unavailable.");
        return false;
      }
      log("loading Porcupine Web SDK…");
      const [porcupineMod, vpMod] = await Promise.all([
        import(/* webpackIgnore: true */ this.sdkPorcupineUrl),
        import(/* webpackIgnore: true */ this.sdkVpUrl),
      ]);
      const PorcupineWorker = porcupineMod.PorcupineWorker || (porcupineMod.default && porcupineMod.default.PorcupineWorker);
      const BuiltInKeyword = porcupineMod.BuiltInKeyword || {};
      this._vp = vpMod.WebVoiceProcessor || (vpMod.default && vpMod.default.WebVoiceProcessor);
      if (!PorcupineWorker || !this._vp) {
        throw new Error("SDK modules missing PorcupineWorker/WebVoiceProcessor exports");
      }

      // Build the keyword spec: a custom .ppn if provided, else a built-in.
      let keywordSpec;
      if (this.keywordUrl) {
        keywordSpec = { publicPath: this.keywordUrl, label: this.keywordLabel, sensitivity: this.sensitivity };
        log("using custom keyword:", this.keywordLabel, "(" + this.keywordUrl + ")");
      } else {
        const builtin = BuiltInKeyword[this.keyword] || this.keyword;
        keywordSpec = { builtin: builtin, sensitivity: this.sensitivity };
        log("using built-in keyword:", this.keyword);
      }

      this._worker = await PorcupineWorker.create(
        this.accessKey,
        keywordSpec,
        (detection) => {
          const label = (detection && (detection.label != null ? detection.label : detection)) || this.keyword;
          log("keyword detected:", label);
          if (typeof this.onKeyword === "function") this.onKeyword(String(label));
        },
        { publicPath: this.modelUrl, forceWrite: true }
      );

      this._ready = true;
      log("ready — say '" + (this.keywordUrl ? this.keywordLabel : this.keyword) + "' to wake Maxi (no beep).");
      return true;
    }

    async listen() {
      if (!this._ready || !this._worker || !this._vp) return;
      if (this._subscribed) return;
      await this._vp.subscribe(this._worker);
      this._subscribed = true;
      log("mic on (listening for wake word)");
    }

    async pause() {
      if (!this._subscribed || !this._worker || !this._vp) return;
      try {
        await this._vp.unsubscribe(this._worker);
      } catch (e) { /* ignore */ }
      this._subscribed = false;
      log("mic released (wake paused)");
    }

    async release() {
      await this.pause();
      if (this._worker) {
        try { this._worker.release && (await this._worker.release()); } catch (e) {}
        try { this._worker.terminate && this._worker.terminate(); } catch (e) {}
      }
      this._worker = null;
      this._ready = false;
      this._initPromise = null;
      log("released");
    }
  }

  global.PorcupineWakeProvider = PorcupineWakeProvider;
})(typeof window !== "undefined" ? window : this);
