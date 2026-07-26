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
 * Hands-free "Hey Maxi" + voice "stop" barge-in via webkitSpeechRecognition need
 * continuous listening, which beeps on this platform. Enable that (beepy) fallback
 * deliberately with { continuous: true } or ?wake=1.
 *
 * THE REAL no-beep hands-free path: pass a `wakeProvider` (an on-device wake-word
 * model over getUserMedia — see porcupine_wake.js). When a ready provider is
 * present, the idle WAKE stage and speaking BARGE_IN stage are handled by the
 * provider (NO webkitSpeechRecognition, so NO beep), and webkitSpeechRecognition is
 * used ONLY to capture the actual question in CAPTURE — one beep per question, like
 * Google Assistant. The provider's mic is released during CAPTURE so the two don't
 * fight over the microphone, then re-acquired afterwards.
 *
 * Modes (set by the page from Maxi's state):
 *   OFF      — mic off (provider released)
 *   WAKE     — idle. provider: beepless wake detection. else push-to-talk (mic OFF)
 *              or continuous (beepy) if enabled.
 *   CAPTURE  — listen for ONE question → onUtterance() (provider paused)
 *   BARGE_IN — Maxi speaking. provider: beepless wake-word interrupt. else
 *              push-to-talk (mic OFF) or continuous barge-in words → onInterrupt().
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

      // Optional on-device wake-word provider (beepless hands-free). When present
      // and ready(), it powers the WAKE + BARGE_IN stages over getUserMedia; its
      // keyword hits are routed here by mode. See porcupine_wake.js.
      this._wakeProvider = opts.wakeProvider || null;
      if (this._wakeProvider) {
        this._wakeProvider.onKeyword = (label) => this._onProviderDetect(label);
      }

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
      this._providerRelease();
    }

    setMode(mode) {
      this._setMode(mode);
      this._applyMode();
    }

    // Re-apply the current mode. Call after the wake provider finishes its async
    // init() so an already-idle engine switches from beepy fallback to beepless.
    reapplyMode() {
      this._applyMode();
    }

    usingProvider() {
      return !!(this._wakeProvider && this._wakeProvider.isReady && this._wakeProvider.isReady());
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
      const provider = this.usingProvider();
      if (this.mode === "CAPTURE") {
        // The question is captured by webkitSpeechRecognition. Release the
        // provider's mic first so the two don't fight over the microphone.
        if (provider) this._providerPause();
        this._beginListen();
      } else if (this.mode === "WAKE" || this.mode === "BARGE_IN") {
        if (provider) {
          // Beepless: the on-device model listens; webkitSpeechRecognition stays off.
          this._endListen();
          this._providerListen();
        } else if (this._continuous) {
          this._beginListen();
        } else {
          this._endListen(); // push-to-talk: silent while idle / speaking
        }
      } else {
        this._endListen();
        if (provider) this._providerPause();
      }
    }

    // -- wake provider control (async, fire-and-forget with internal guards) ---
    _providerListen() {
      const p = this._wakeProvider;
      if (!p || !p.isReady || !p.isReady()) return;
      Promise.resolve()
        .then(() => p.listen())
        .catch((e) => this.onError("wake-provider-listen: " + (e && e.message || e)));
    }
    _providerPause() {
      const p = this._wakeProvider;
      if (!p || !p.pause) return;
      Promise.resolve()
        .then(() => p.pause())
        .catch(() => {});
    }
    _providerRelease() {
      const p = this._wakeProvider;
      if (!p || !p.release) return;
      Promise.resolve()
        .then(() => p.release())
        .catch(() => {});
    }

    // A wake-word hit from the on-device model. Route it by the current mode:
    // idle → wake Maxi; speaking → barge-in (echo-safe: Maxi never says its own
    // wake word). Ignored otherwise.
    _onProviderDetect(label) {
      const now = Date.now();
      this._lastHeard = "[wake:" + (label || "?") + "]";
      if (this.mode === "WAKE") {
        this._decide("WAKE (provider: " + label + ")");
        this.onWake(label || "");
      } else if (this.mode === "BARGE_IN") {
        if (this._speakingSince && now - this._speakingSince < ONSET_DEAF_MS) {
          return this._decide("ignored: onset-deafness");
        }
        if (now - this._lastBargeAt < COOLDOWN_MS) {
          return this._decide("ignored: cooldown");
        }
        this._lastBargeAt = now;
        this._decide("BARGE-IN (provider: " + label + ")");
        this.onInterrupt(label || "");
      } else {
        this._decide("ignored provider hit in mode " + this.mode);
      }
      this._hud();
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
        // Never restart in idle push-to-talk mode — that is the beep storm. And when
        // an on-device wake provider owns WAKE/BARGE_IN, never restart there either.
        const keepGoing =
          this._wantRunning &&
          (this.mode === "CAPTURE" ||
            (this._continuous &&
              !this.usingProvider() &&
              (this.mode === "WAKE" || this.mode === "BARGE_IN")));
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
        // Send an utterance that PRESERVES math operators. `normalize()` strips
        // symbols (so "2 + 2" would become "2 2" and lose the "+"); here we keep
        // +, -, ×, ÷, = so the math parser can see the operation.
        const utterance = finalText
          .toLowerCase()
          .replace(/\s+/g, " ")
          .trim();
        // Got the question. Stop listening immediately and DON'T let onend
        // restart the recognizer (that caused a stray extra mic beep before
        // processing). Maxi will now think; the backend drives the next state.
        this._setMode("OFF");
        this._endListen();
        this.onUtterance(utterance || norm, finalConf || 1);
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
      const modeLabel = this.usingProvider()
        ? "hands-free (wake-model)"
        : this._continuous
          ? "hands-free (beepy)"
          : "tap-to-talk";
      this._hudEl.textContent =
        "🎙 Maxi voice (" + modeLabel + ")\n" +
        "mode:     " + this.mode + (this._listening ? " (mic on)" : " (mic off)") + "\n" +
        "heard:    " + (this._lastHeard || "—") + "\n" +
        "script:   " + (this._recentScripts.slice(-1)[0] || "—") + "\n" +
        "decision: " + (this._lastDecision || "—");
    }
  }

  global.MaxiVoiceEngine = MaxiVoiceEngine;
})(typeof window !== "undefined" ? window : this);
