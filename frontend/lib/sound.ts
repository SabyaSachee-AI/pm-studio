/**
 * Soft, non-intrusive UI sounds generated with the Web Audio API.
 * No audio asset files — synthesised on demand so nothing autoplays unexpectedly.
 */

let ctx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
  }
  return ctx;
}

/** A gentle two-note "ding" — used when an AI job finishes successfully. */
export function playCompletionChime(): void {
  const audio = getCtx();
  if (!audio) return;
  // Browsers suspend the context until a user gesture; resume best-effort.
  if (audio.state === "suspended") void audio.resume();

  const now = audio.currentTime;
  const notes = [
    { freq: 660, start: 0, dur: 0.18 },   // E5
    { freq: 880, start: 0.12, dur: 0.28 }, // A5
  ];

  for (const n of notes) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = "sine";
    osc.frequency.value = n.freq;

    const t0 = now + n.start;
    // Soft attack + smooth exponential release — no harsh clicks
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.12, t0 + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + n.dur);

    osc.connect(gain);
    gain.connect(audio.destination);
    osc.start(t0);
    osc.stop(t0 + n.dur + 0.02);
  }
}

// ---------------------------------------------------------------------------
// Ambient generation loop — a relaxed, smooth "blip" tone that plays softly
// while an AI job runs, and stops automatically when it finishes.
// ---------------------------------------------------------------------------

let ambientTimer: ReturnType<typeof setInterval> | null = null;
let ambientPad: { osc: OscillatorNode; gain: GainNode } | null = null;

/** Play a single soft, warm blip (two gentle sine notes). */
function playSoftBlip(): void {
  const audio = getCtx();
  if (!audio) return;
  const now = audio.currentTime;
  // Calm interval: a soft perfect-fifth shimmer
  const notes = [
    { freq: 523.25, start: 0, dur: 0.5 },    // C5
    { freq: 783.99, start: 0.18, dur: 0.6 }, // G5
  ];
  for (const n of notes) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = "sine";
    osc.frequency.value = n.freq;
    const t0 = now + n.start;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.05, t0 + 0.12); // very soft
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + n.dur);
    osc.connect(gain);
    gain.connect(audio.destination);
    osc.start(t0);
    osc.stop(t0 + n.dur + 0.05);
  }
}

/** Start the relaxed ambient loop. Idempotent — safe to call repeatedly. */
export function startAmbientLoop(): void {
  const audio = getCtx();
  if (!audio) return;
  if (audio.state === "suspended") void audio.resume();
  if (ambientTimer || ambientPad) return; // already running

  // Quiet warm drone underneath the blips
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = "sine";
  osc.frequency.value = 196; // G3 — low and unobtrusive
  gain.gain.setValueAtTime(0.0001, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.018, audio.currentTime + 1.5);
  osc.connect(gain);
  gain.connect(audio.destination);
  osc.start();
  ambientPad = { osc, gain };

  // Gentle recurring blip every ~4s
  playSoftBlip();
  ambientTimer = setInterval(playSoftBlip, 4000);
}

/** Stop the ambient loop with a smooth fade-out. */
export function stopAmbientLoop(): void {
  if (ambientTimer) {
    clearInterval(ambientTimer);
    ambientTimer = null;
  }
  const audio = getCtx();
  if (ambientPad && audio) {
    const { osc, gain } = ambientPad;
    const now = audio.currentTime;
    try {
      gain.gain.cancelScheduledValues(now);
      gain.gain.setValueAtTime(Math.max(gain.gain.value, 0.0001), now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.6);
      osc.stop(now + 0.65);
    } catch {
      /* already stopped */
    }
    ambientPad = null;
  }
}

/** A short, low "thunk" — used when an AI job fails. */
export function playErrorTone(): void {
  const audio = getCtx();
  if (!audio) return;
  if (audio.state === "suspended") void audio.resume();

  const now = audio.currentTime;
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(340, now);
  osc.frequency.exponentialRampToValueAtTime(180, now + 0.25);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.1, now + 0.03);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.3);
  osc.connect(gain);
  gain.connect(audio.destination);
  osc.start(now);
  osc.stop(now + 0.32);
}
