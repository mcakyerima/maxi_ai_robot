/**
 * MaxiVoiceEngine — continuous wake word + self-echo-safe barge-in for the tablet.
 *
 * THE PROBLEM THIS SOLVES: Maxi's speaker and mic are inches apart. When Maxi
 * talks, its own mic hears it. A naive "stop when you hear speech" design makes
 * Maxi interrupt itself. This engine defeats that with layered defenses (see
 * docs/BARGE_IN.md):
 *
 *   Layer 1 — Keyword-gated: only explicit trigger words ("stop", "maxi", "wait")
 *             can interrupt. Arbitrary sound never does.
 *   Layer 2 — Self-echo rejection: the backend tells us EXACTLY what Maxi is
 *             saying (`speaking_script`). Any recognized phrase that belongs to
 *             Maxi's own script is ignored. This is the key trick.
 *   Layer 4 — Timing gates: ignore the first ~350ms of playback (loudest echo),
 *             cooldown after a barge-in, and a confidence floor.
 *
 * One recognizer, three modes (webkitSpeechRecognition allows one healthy
 * instance and auto-stops on silence, so we restart it and swap MODE, never
 * instances):
 *   WAKE     — Maxi idle: listen for "Hey Maxi" → onWake()
 *   CAPTURE  — Maxi listening: capture the child's question → onUtterance()
 *   BARGE_IN — Maxi speaking: listen for trigger words (Layers 1/2/4) → onInterrupt()
 *   OFF      — recognizer stopped
 */
(function (global) {
  "use strict";

  const DEFAULT_WAKE_WORDS = ["hey maxi", "hi maxi", "hello maxi", "okay maxi", "maxi"];
  const DEFAULT_INTERRUPT_WORDS = [
    "stop", "stop maxi", "maxi stop", "wait", "hold on", "pause",
    "be quiet", "quiet", "shush", "hush", "okay maxi", "hey maxi",
  ];

  const ONSET_DEAF_MS = 350;   // ignore echo transient right when audio starts
  const COOLDOWN_MS = 800;     // after a valid barge-in, don't re-fire
  const MIN_CONFIDENCE = 0.55; // drop low-confidence final results
  const SCRIPT_MEMORY = 6;     // how many recent sentences of Maxi's script to remember

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

      // callbacks
      this.onWake = opts.onWake || function () {};
      this.onUtterance = opts.onUtterance || function () {};
      this.onInterrupt = opts.onInterrupt || function () {};
      this.onInterim = opts.onInterim || function () {};
      this.onModeChange = opts.onModeChange || function () {};
      this.onError = opts.onError || function () {};

      this.mode = "OFF";
      this._recognition = null;
      this._wantRunning = false;
      this._restarting = false;

      // Layer 2 state — what Maxi is currently saying.
      this._scriptWords = new Set();
      this._recentScripts = [];
      this._speakingSince = 0;
      this._lastBargeAt = 0;

      this._supported =
        typeof window !== "undefined" &&
        ("webkitSpeechRecognition" in window || "SpeechRecognition" in window);

      // Optional on-screen debug HUD — enable with ?maxidebug=1 on the URL
      // (or pass { debug: true }). Shows mode, last heard phrase, and every
      // barge-in decision + reason, so thresholds can be tuned from real data.
      this._debug =
        !!opts.debug ||
        (typeof window !== "undefined" &&
          typeof window.location !== "undefined" &&
          /[?&]maxidebug/.test(window.location.search || ""));
      this._hudEl = null;
      this._lastHeard = "";
      this._lastDecision = "";
    }

    isSupported() {
      return this._supported;
    }

    // -- lifecycle ---------------------------------------------------------
    start() {
      if (!this._supported) {
        this.onError("speech-recognition-unsupported");
        return;
      }
      this._wantRunning = true;
      this._hudInit();
      this._ensureRecognition();
      this._safeStart();
    }

    stop() {
      this._wantRunning = false;
      if (this._recognition) {
        try { this._recognition.stop(); } catch (e) {}
      }
      this._setMode("OFF");
    }

    setMode(mode) {
      this._setMode(mode);
      if (mode !== "OFF" && this._wantRunning) this._safeStart();
    }

    _setMode(mode) {
      if (this.mode === mode) return;
      this.mode = mode;
      this.onModeChange(mode);
      this._hud();
    }

    /**
     * Tell the engine what Maxi is saying NOW (called on each `speaking_script`).
     * Enters BARGE_IN listening and refreshes the echo-rejection vocabulary.
     */
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
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = "en-US";
      rec.maxAlternatives = 1;

      rec.onresult = (event) => this._onResult(event);
      rec.onerror = (event) => {
        // "no-speech"/"aborted" are normal; just let onend restart us.
        if (event.error && event.error !== "no-speech" && event.error !== "aborted") {
          this.onError(event.error);
        }
      };
      rec.onend = () => {
        // Android Chrome stops on silence — restart to stay always-listening.
        if (this._wantRunning && this.mode !== "OFF") {
          this._restarting = true;
          setTimeout(() => this._safeStart(), 200);
        }
      };
      this._recognition = rec;
    }

    _safeStart() {
      if (!this._recognition || !this._wantRunning) return;
      try {
        this._recognition.start();
        this._restarting = false;
      } catch (e) {
        // start() throws if already started — that's fine.
      }
    }

    // -- the brain: decide what a recognition result means ----------------
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
        // Act on interim too — barge-in must feel instant.
        this._handleBargeIn(interimNorm || normalize(finalText), finalConf, !!finalText);
        return;
      }

      if (!finalText) return;
      const norm = normalize(finalText);
      if (this.mode === "WAKE") {
        if (this._matchesAny(norm, this.wakeWords)) {
          this.onWake(norm);
        }
      } else if (this.mode === "CAPTURE") {
        if (finalConf && finalConf < MIN_CONFIDENCE) return;
        if (!norm) return;
        // Safety: if we somehow capture Maxi's own recent words (tail audio /
        // echo right after it finished), don't treat it as the child's question.
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

      // Layer 4a — onset deafness: skip the loud echo right at playback start.
      if (this._speakingSince && now - this._speakingSince < ONSET_DEAF_MS) {
        return this._decide("ignored: onset-deafness");
      }
      // Layer 4b — cooldown: one "stop" shouldn't fire twice.
      if (now - this._lastBargeAt < COOLDOWN_MS) {
        return this._decide("ignored: cooldown");
      }

      // Which trigger word(s) appear in what we heard?
      const heardTriggers = this.interruptWords.filter((w) => this._contains(phrase, w));
      if (heardTriggers.length === 0) {
        return this._decide("ignored: no trigger word");
      }

      // Layer 2 — self-echo rejection: if EVERY heard trigger is part of Maxi's
      // own current script, this is Maxi hearing itself. Ignore it.
      const childSaidIt = heardTriggers.some((w) => !this._triggerInScript(w));
      if (!childSaidIt) {
        return this._decide("ignored: self-echo (" + heardTriggers.join(",") + ")");
      }

      // A real barge-in from the child.
      this._lastBargeAt = now;
      this._decide("BARGE-IN! (" + heardTriggers.join(",") + ")");
      this.onInterrupt(phrase);
    }

    _decide(text) {
      this._lastDecision = text;
      this._hud();
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
        "🎙 Maxi voice\n" +
        "mode:     " + this.mode + "\n" +
        "heard:    " + (this._lastHeard || "—") + "\n" +
        "script:   " + (this._recentScripts.slice(-1)[0] || "—") + "\n" +
        "decision: " + (this._lastDecision || "—");
    }

    // -- matching helpers --------------------------------------------------
    _contains(haystack, needle) {
      // word-boundary-ish containment so "stop" doesn't match "stopwatch".
      return (" " + haystack + " ").indexOf(" " + needle + " ") !== -1;
    }

    _matchesAny(phrase, words) {
      return words.some((w) => this._contains(phrase, w) || phrase === w);
    }

    _triggerInScript(word) {
      // Every token of the trigger appears in Maxi's recent script → it's echo.
      return word.split(" ").every((tok) => this._scriptWords.has(tok));
    }

    _isEcho(phrase) {
      // Treat a phrase as Maxi's own echo when we have a recent script and most
      // of the phrase's words belong to it.
      if (!this._scriptWords || this._scriptWords.size === 0) return false;
      const words = phrase.split(" ").filter(Boolean);
      if (words.length === 0) return false;
      const inScript = words.filter((w) => this._scriptWords.has(w)).length;
      return inScript / words.length >= 0.8;
    }
  }

  global.MaxiVoiceEngine = MaxiVoiceEngine;
})(typeof window !== "undefined" ? window : this);
