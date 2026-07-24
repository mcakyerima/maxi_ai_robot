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

function makeEngine() {
  const events = { wake: [], utter: [], interrupt: [] };
  const engine = new MaxiVoiceEngine({
    onWake: (t) => events.wake.push(t),
    onUtterance: (t) => events.utter.push(t),
    onInterrupt: (t) => events.interrupt.push(t),
  });
  return { engine, events };
}

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

console.log(failures === 0 ? "\nALL VOICE-ENGINE TESTS PASSED" : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
