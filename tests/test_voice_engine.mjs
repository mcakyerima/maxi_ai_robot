/**
 * Self-audit for MaxiVoiceEngine's decision logic (no browser needed).
 * We stub `window` with a dummy SpeechRecognition, then drive the pure logic.
 *
 * Run:  node tests/test_voice_engine.mjs
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// --- minimal browser stub ---
class FakeRecognition {
  start() {}
  stop() {}
}
const win = { webkitSpeechRecognition: FakeRecognition, SpeechRecognition: FakeRecognition };
globalThis.window = win;

// Load the engine (it attaches MaxiVoiceEngine to the global `window`).
const src = readFileSync(path.join(__dirname, "..", "ui", "static", "js", "maxi_voice_engine.js"), "utf8");
new Function("window", src)(win);
const MaxiVoiceEngine = win.MaxiVoiceEngine;

let failures = 0;
function check(name, cond) {
  console.log(`${cond ? "PASS" : "FAIL"}: ${name}`);
  if (!cond) failures++;
}

function makeEngine(extra) {
  const events = { wake: [], utter: [], interrupt: [] };
  const engine = new MaxiVoiceEngine(
    Object.assign(
      {
        onWake: (t) => events.wake.push(t),
        onUtterance: (t) => events.utter.push(t),
        onInterrupt: (t) => events.interrupt.push(t),
      },
      extra || {},
    ),
  );
  return { engine, events };
}

// A stand-in on-device wake provider (Porcupine's contract), no browser/network.
class FakeWakeProvider {
  constructor() {
    this.ready = true;
    this.onKeyword = null; // set by the engine
    this.listenCount = 0;
    this.pauseCount = 0;
    this.releaseCount = 0;
    this.subscribed = false;
  }
  isReady() { return this.ready; }
  async init() { this.ready = true; return true; }
  async listen() { this.listenCount++; this.subscribed = true; }
  async pause() { this.pauseCount++; this.subscribed = false; }
  async release() { this.releaseCount++; this.subscribed = false; }
  fire(label) { if (this.onKeyword) this.onKeyword(label); } // simulate a detection
}
const tick = () => new Promise((r) => setTimeout(r, 0)); // flush provider microtasks

// Scenario A: Maxi says "please don't ever stop learning"; mic echoes "stop".
{
  const { engine, events } = makeEngine();
  engine.setMode("BARGE_IN");
  engine.setScript("please don't ever stop learning");
  engine._speakingSince = Date.now() - 1000; // past onset window
  engine._handleBargeIn("stop", 0.95, true);
  check("A: Maxi's own 'stop' is IGNORED (self-echo)", events.interrupt.length === 0);
}

// Scenario B: Child says "stop maxi" while Maxi says "the sun is very hot".
{
  const { engine, events } = makeEngine();
  engine.setMode("BARGE_IN");
  engine.setScript("the sun is very hot");
  engine._speakingSince = Date.now() - 1000;
  engine._handleBargeIn("stop maxi", 0.95, true);
  check("B: child's 'stop maxi' DOES interrupt", events.interrupt.length === 1);
}

// Scenario C: onset deafness — trigger within 350ms of playback is ignored.
{
  const { engine, events } = makeEngine();
  engine.setMode("BARGE_IN");
  engine.setScript("the moon is bright");
  engine._speakingSince = Date.now(); // just started
  engine._handleBargeIn("stop", 0.95, true);
  check("C: onset deafness ignores immediate echo", events.interrupt.length === 0);
}

// Scenario D: cooldown — a second barge-in right after the first is suppressed.
{
  const { engine, events } = makeEngine();
  engine.setMode("BARGE_IN");
  engine.setScript("we are learning shapes");
  engine._speakingSince = Date.now() - 1000;
  engine._handleBargeIn("wait", 0.95, true);
  engine._handleBargeIn("wait", 0.95, true); // immediate repeat
  check("D: cooldown fires interrupt only once", events.interrupt.length === 1);
}

// Scenario E: wake word while idle.
{
  const { engine, events } = makeEngine();
  engine.setMode("WAKE");
  engine._onResult({
    resultIndex: 0,
    results: [Object.assign([{ transcript: "hey maxi", confidence: 0.9 }], { isFinal: true })],
  });
  check("E: 'hey maxi' triggers wake", events.wake.length === 1);
}

// Scenario F: random chatter while speaking does NOT interrupt (no trigger word).
{
  const { engine, events } = makeEngine();
  engine.setMode("BARGE_IN");
  engine.setScript("plants need sunlight");
  engine._speakingSince = Date.now() - 1000;
  engine._handleBargeIn("i like cats and dogs", 0.9, true);
  check("F: non-trigger chatter is ignored", events.interrupt.length === 0);
}

// Scenario G: child says a trigger that ALSO happens to be in Maxi's script,
// but says extra words too — still counts because a non-echo trigger path exists.
{
  const { engine, events } = makeEngine();
  engine.setMode("BARGE_IN");
  engine.setScript("don't stop now");   // Maxi's script contains "stop"
  engine._speakingSince = Date.now() - 1000;
  engine._handleBargeIn("maxi stop", 0.95, true); // child: "maxi stop" — "maxi" not in script
  check("G: child 'maxi stop' interrupts even if 'stop' is in script", events.interrupt.length === 1);
}

// --- Hands-free wake-provider integration (beepless "Hey Maxi") ---------------
// Scenario H+I: a ready provider owns WAKE (beepless) and its hit wakes Maxi.
{
  const p = new FakeWakeProvider();
  const { engine, events } = makeEngine({ wakeProvider: p });
  engine.start();
  engine.setMode("WAKE");
  await tick();
  check("H: provider listens in WAKE, webkitSpeechRecognition stays OFF (no beep)",
    engine.usingProvider() && p.listenCount >= 1 && engine._listening === false);
  p.fire("Computer");
  check("I: provider keyword in WAKE → onWake", events.wake.length === 1);

  // Scenario J: CAPTURE releases the provider mic and starts recognition (one beep).
  engine.setMode("CAPTURE");
  await tick();
  check("J: CAPTURE pauses provider mic AND starts recognition",
    p.pauseCount >= 1 && engine._listening === true);
}

// Scenario K: provider keyword during BARGE_IN interrupts (echo-safe by design).
{
  const p = new FakeWakeProvider();
  const { engine, events } = makeEngine({ wakeProvider: p });
  engine.start();
  engine.setMode("BARGE_IN");
  engine._speakingSince = Date.now() - 1000; // past onset-deafness window
  await tick();
  p.fire("Computer");
  check("K: provider keyword in BARGE_IN → onInterrupt", events.interrupt.length === 1);
}

// Scenario L: onset-deafness still applies to provider barge-in hits.
{
  const p = new FakeWakeProvider();
  const { engine, events } = makeEngine({ wakeProvider: p });
  engine.start();
  engine.setMode("BARGE_IN");
  engine._speakingSince = Date.now(); // just started speaking
  await tick();
  p.fire("Computer");
  check("L: provider barge-in within onset window is ignored", events.interrupt.length === 0);
}

// Scenario M: a NOT-ready provider → graceful fallback to push-to-talk (mic off).
{
  const p = new FakeWakeProvider();
  p.ready = false;
  const { engine } = makeEngine({ wakeProvider: p });
  engine.start();
  engine.setMode("WAKE");
  await tick();
  check("M: not-ready provider → fallback (provider unused, mic off in WAKE)",
    engine.usingProvider() === false && p.listenCount === 0 && engine._listening === false);

  // Scenario N: once it becomes ready, reapplyMode() switches to beepless.
  p.ready = true;
  engine.reapplyMode();
  await tick();
  check("N: reapplyMode() switches to beepless once provider is ready", p.listenCount >= 1);
}

// Scenario O: NO provider → original push-to-talk behavior is unchanged.
{
  const { engine } = makeEngine();
  engine.start();
  engine.setMode("WAKE");
  check("O: no provider → push-to-talk (mic OFF in idle WAKE)",
    engine.usingProvider() === false && engine._listening === false);
}

// Scenario P: a WAKE-ONLY provider (supportsBargeIn=false, e.g. Vosk) must NOT
// listen while Maxi speaks — the mic is released, so Maxi can't self-interrupt.
{
  const p = new FakeWakeProvider();
  p.supportsBargeIn = false;
  const { engine, events } = makeEngine({ wakeProvider: p });
  engine.start();
  engine.setMode("WAKE");
  await tick();
  const listenedInWake = p.listenCount;
  engine.setMode("BARGE_IN");
  await tick();
  check("P: wake-only provider releases the mic while speaking (no barge-in)",
    p.listenCount === listenedInWake && p.pauseCount >= 1 && engine._listening === false);
  // And a stray hit while speaking does nothing (provider isn't even listening).
  p.fire("hey maxi");
  check("P2: wake-only provider can't fire an interrupt while speaking",
    events.interrupt.length === 0);
}

console.log(failures === 0 ? "\nALL VOICE-ENGINE TESTS PASSED" : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
