/**
 * MaxiVoiceEngine — microphone control for the tablet.
 *
 * IMPORTANT PLATFORM NOTE
 * -----------------------
 * Android Chrome's webkitSpeechRecognition plays a system BEEP on every start and
 * stop, and auto-stops after a short silence. Running it *continuously* therefore
 * produces a constant on/off beeping and never lets anyone speak. So by default
 * this engine is PUSH-TO-TALK: the mic is off while idle, and only listens for a
 * single question after the child taps the mic (or Maxi enters LISTENING). That
 * gives one beep-in / one beep-out per question, like Google Assistant.
 *
 * Hands-free "Hey Maxi" + voice "stop" barge-in need continuous listening, which
 * beeps on this platform. Enable it deliberately with { continuous: true } or by
 * adding ?wake=1 to the URL. The real no-beep solution is a dedicated on-device
 * wake-word model (Porcupine / openWakeWord over getUserMedia) — see docs/BARGE_IN.md.
 *
 * Modes (set by the page from Maxi's state):
 *   OFF      — mic off
 *   WAKE     — idle. push-to-talk: mic OFF (silent). continuous: listen for wake words.
 *   CAPTURE  — listen for ONE question → onUtterance()
 *   BARGE_IN — Maxi speaking. push-to-talk: mic OFF (use the mic button to interrupt).
 *              continuous: listen for barge-in words, echo-filtered → onInterrupt().
 */
(function (global) {
  "use strict";

  const DEFAULT_WAKE_WORDS = ["hey maxi", "hi maxi", "hello maxi", "okay maxi", "maxi"];
  const DEFAULT_INTERRUPT_WORDS = [
    "stop", "stop maxi", "maxi stop", "wait", "hold on", "pause",
    "be quiet", "quiet", "shush", "hush", "okay maxi", "hey maxi",
  ];

  const ONSET_DEAF_MS = 350;
  const COOLDOWN_MS = 800;
  const MIN_CONFIDENCE = 0.5;
  const SCRIPT_MEMORY = 6;
  const RESTART_DELAY_MS = 350;

  const hasWindow = typeof window !== "undefined";

  function normalize(text) {
    return (text || "")
      .toLowerCase()
      .replace(/[^\w\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  class MaxiVoiceEngine {
    constructor(opts) {
      opts = opts || {};
      this.wakeWords = (opts.wakeWords || DEFAULT_WAKE_WORDS).map(normalize);
      this.interruptWords = (opts.interruptWords || DEFAULT_INTERRUPT_WORDS).map(normalize);

      this.onWake = opts.onWake || function () {};
      this.onUtterance = opts.onUtterance || function () {};
      this.onInterrupt = opts.onInterrupt || function () {};
      this.onInterim = opts.onInterim || function () {};
      this.onModeChange = opts.onModeChange || function () {};
      this.onError = opts.onError || function () {};

      // Continuous (hands-free, beepy) listening is OFF by default. Opt in with
      // { continuous:true } or ?wake=1 on the URL.
      this._continuous =
        !!opts.continuous ||
        (hasWindow &&
          typeof window.location !== "undefined" &&
          /[?&](wake|continuous)=1/.test(window.location.search || ""));

      this.mode = "OFF";
      this._recognition = null;
      this._wantRunning = false;
      this._listening = false;

      this._scriptWords = new Set();
      this._recentScripts = [];
      this._speakingSince = 0;
      this._lastBargeAt = 0;

      this._supported =
        hasWindow &&
        ("webkitSpeechRecognition" in window || "SpeechRecognition" in window);

      this._debug =
        !!opts.debug ||
        (hasWindow &&
          typeof window.location !== "undefined" &&
          /[?&]maxidebug/.test(window.location.search || ""));
      this._hudEl = null;
      this._lastHeard = "";
      this._lastDecision = "";
    }

    isSupported() { return this._supported; }
    continuousEnabled() { return this._continuous; }

    // -- lifecycle ---------------------------------------------------------
    start() {
      if (!this._supported) {
        this.onError("speech-recognition-unsupported");
        return;
      }
      this._wantRunning = true;
      this._hudInit();
      this._ensureRecognition();
      this._applyMode();
    }

    stop() {
      this._wantRunning = false;
      this._setMode("OFF");
      this._endListen();
    }

    setMode(mode) {
      this._setMode(mode);
      this._applyMode();
    }

    _setMode(mode) {
      if (this.mode === mode) return;
      this.mode = mode;
      this.onModeChange(mode);
      this._hud();
    }

    // Turn the mic on/off to match the current mode.
    _applyMode() {
      if (!this._wantRunning) return;
      if (this.mode === "CAPTURE") {
        this._beginListen();
      } else if (this.mode === "WAKE" || this.mode === "BARGE_IN") {
        if (this._continuous) this._beginListen();
        else this._endListen(); // push-to-talk: silent while idle / speaking
      } else {
        this._endListen();
      }
    }

    setScript(text) {
      const norm = normalize(text);
      if (!norm) return;
      this._recentScripts.push(norm);
      if (this._recentScripts.length > SCRIPT_MEMORY) this._recentScripts.shift();
      this._scriptWords = new Set(this._recentScripts.join(" ").split(" "));
      this._speakingSince = Date.now();
      if (this.mode !== "BARGE_IN") this.setMode("BARGE_IN");
    }

    clearScript() {
      this._scriptWords = new Set();
      this._recentScripts = [];
      this._speakingSince = 0;
    }

    // -- recognizer plumbing ----------------------------------------------
    _ensureRecognition() {
      if (this._recognition) return;
      const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
      const rec = new Ctor();
      rec.continuous = false; // single-utterance; WE decide when to listen again
      rec.interimResults = true;
      rec.lang = "en-US";
      rec.maxAlternatives = 1;

      rec.onresult = (event) => this._onResult(event);
      rec.onerror = (event) => {
        if (event.error && event.error !== "no-speech" && event.error !== "aborted") {
          this.onError(event.error);
        }
      };
      rec.onend = () => {
        this._listening = false;
        // Re-listen ONLY while capturing a question, or for continuous wake/barge-in.
        // Never restart in idle push-to-talk mode — that is the beep storm.
        const keepGoing =
          this._wantRunning &&
          (this.mode === "CAPTURE" ||
            (this._continuous && (this.mode === "WAKE" || this.mode === "BARGE_IN")));
        if (keepGoing) setTimeout(() => this._beginListen(), RESTART_DELAY_MS);
      };
      this._recognition = rec;
    }

    _beginListen() {
      if (!this._recognition || this._listening) return;
      try {
        this._recognition.start();
        this._listening = true;
      } catch (e) {
        /* start() throws if already running — fine */
      }
    }

    _endListen() {
      if (!this._recognition || !this._listening) return;
      try {
        this._recognition.stop();
      } catch (e) {
        /* ignore */
      }
      this._listening = false;
    }

    // -- decide what a recognition result means ---------------------------
    _onResult(event) {
      let interim = "";
      let finalText = "";
      let finalConf = 0;
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        const alt = res[0];
        if (res.isFinal) {
          finalText += alt.transcript;
          finalConf = alt.confidence || finalConf;
        } else {
          interim += alt.transcript;
        }
      }

      const interimNorm = normalize(interim);
      if (interimNorm) {
        this._lastHeard = interimNorm;
        this.onInterim(interimNorm);
        this._hud();
      }
      if (finalText) {
        this._lastHeard = normalize(finalText);
        this._hud();
      }

      if (this.mode === "BARGE_IN") {
        this._handleBargeIn(interimNorm || normalize(finalText), finalConf, !!finalText);
        return;
      }
      if (!finalText) return;
      const norm = normalize(finalText);
      if (this.mode === "WAKE") {
        if (this._matchesAny(norm, this.wakeWords)) this.onWake(norm);
      } else if (this.mode === "CAPTURE") {
        if (finalConf && finalConf < MIN_CONFIDENCE) return;
        if (!norm) return;
        if (this._isEcho(norm)) {
          this._decide("ignored capture: self-echo");
          return;
        }
        this.onUtterance(norm, finalConf || 1);
      }
    }

    _handleBargeIn(phrase, confidence, isFinal) {
      if (!phrase) return;
      const now = Date.now();
      if (this._speakingSince && now - this._speakingSince < ONSET_DEAF_MS) {
        return this._decide("ignored: onset-deafness");
      }
      if (now - this._lastBargeAt < COOLDOWN_MS) {
        return this._decide("ignored: cooldown");
      }
      const heardTriggers = this.interruptWords.filter((w) => this._contains(phrase, w));
      if (heardTriggers.length === 0) {
        return this._decide("ignored: no trigger word");
      }
      const childSaidIt = heardTriggers.some((w) => !this._triggerInScript(w));
      if (!childSaidIt) {
        return this._decide("ignored: self-echo (" + heardTriggers.join(",") + ")");
      }
      this._lastBargeAt = now;
      this._decide("BARGE-IN! (" + heardTriggers.join(",") + ")");
      this.onInterrupt(phrase);
    }

    _decide(text) {
      this._lastDecision = text;
      this._hud();
    }

    // -- matching helpers --------------------------------------------------
    _contains(haystack, needle) {
      return (" " + haystack + " ").indexOf(" " + needle + " ") !== -1;
    }
    _matchesAny(phrase, words) {
      return words.some((w) => this._contains(phrase, w) || phrase === w);
    }
    _triggerInScript(word) {
      return word.split(" ").every((tok) => this._scriptWords.has(tok));
    }
    _isEcho(phrase) {
      if (!this._scriptWords || this._scriptWords.size === 0) return false;
      const words = phrase.split(" ").filter(Boolean);
      if (words.length === 0) return false;
      const inScript = words.filter((w) => this._scriptWords.has(w)).length;
      return inScript / words.length >= 0.8;
    }

    // -- debug HUD ---------------------------------------------------------
    _hudInit() {
      if (!this._debug || typeof document === "undefined" || this._hudEl) return;
      const el = document.createElement("div");
      el.id = "maxi-voice-hud";
      el.style.cssText =
        "position:fixed;bottom:8px;left:8px;z-index:99999;max-width:60vw;" +
        "font:12px/1.4 monospace;color:#fff;background:rgba(0,0,0,.78);" +
        "padding:8px 10px;border-radius:8px;pointer-events:none;white-space:pre-wrap;";
      document.body.appendChild(el);
      this._hudEl = el;
      this._hud();
    }
    _hud() {
      if (!this._hudEl) return;
      this._hudEl.textContent =
        "🎙 Maxi voice (" + (this._continuous ? "hands-free" : "tap-to-talk") + ")\n" +
        "mode:     " + this.mode + (this._listening ? " (mic on)" : " (mic off)") + "\n" +
        "heard:    " + (this._lastHeard || "—") + "\n" +
        "script:   " + (this._recentScripts.slice(-1)[0] || "—") + "\n" +
        "decision: " + (this._lastDecision || "—");
    }
  }

  global.MaxiVoiceEngine = MaxiVoiceEngine;
})(typeof window !== "undefined" ? window : this);
