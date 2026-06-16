"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ─── Radio stations ───────────────────────────────────────────────────────────
const STATIONS = [
  { id: "groove", name: "Groove Salad", genre: "Ambient",   url: "https://ice1.somafm.com/groovesalad-64-aac" },
  { id: "drone",  name: "Drone Zone",   genre: "Drone",     url: "https://ice1.somafm.com/dronezone-64-aac"  },
  { id: "lush",   name: "Lush",         genre: "Downtempo", url: "https://ice1.somafm.com/lush-64-aac"       },
  { id: "agent",  name: "Secret Agent", genre: "Jazz/Spy",  url: "https://ice1.somafm.com/secretagent-64-aac"},
];

// ─── Synth presets ────────────────────────────────────────────────────────────
const PRESETS = {
  ambient: { label: "Ambient", icon: "ti-leaf",  desc: "Dreamy melody" },
  focus:   { label: "Focus",   icon: "ti-brain", desc: "Lo-fi beat"    },
  lounge:  { label: "Lounge",  icon: "ti-music", desc: "Walking bass"  },
  bip:     { label: "Bip",     icon: "ti-radar", desc: "Soft pulse"    },
} as const;
type Preset = keyof typeof PRESETS;
type Tab    = "synth" | "local" | "radio";

const AMBIENT_MELODY = [220, 261.6, 293.7, 329.6, 392, 440, 392, 329.6, 261.6, 293.7];
const AMBIENT_PAD    = [110, 130.8, 164.8, 196, 261.6, 329.6];
const FOCUS_MELODY   = [261.6, 329.6, 392, 349.2, 293.7, 329.6, 261.6, 293.7];
const FOCUS_BASS     = [65.4, 98, 130.8, 98];
const LOUNGE_BASS    = [146.8, 174.6, 185, 196, 174.6, 164.8, 146.8, 130.8];
const LOUNGE_PAD     = [146.8, 174.6, 220, 261.6, 293.7, 349.2];

const AUDIO_EXT = /\.(mp3|flac|wav|ogg|aac|m4a|opus)$/i;

// ─── IndexedDB helpers (persist folder handle) ────────────────────────────────
function openIDB(): Promise<IDBDatabase> {
  return new Promise((res, rej) => {
    const req = indexedDB.open("pm-studio-music", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("handles");
    req.onsuccess = () => res(req.result);
    req.onerror   = () => rej(req.error);
  });
}
async function saveHandle(h: FileSystemDirectoryHandle) {
  const db = await openIDB();
  return new Promise<void>((res, rej) => {
    const req = db.transaction("handles", "readwrite").objectStore("handles").put(h, "dir");
    req.onsuccess = () => res();
    req.onerror   = () => rej(req.error);
  });
}
async function loadHandle(): Promise<FileSystemDirectoryHandle | null> {
  const db = await openIDB();
  return new Promise((res, rej) => {
    const req = db.transaction("handles", "readonly").objectStore("handles").get("dir");
    req.onsuccess = () => res((req.result as FileSystemDirectoryHandle | undefined) ?? null);
    req.onerror   = () => rej(req.error);
  });
}

// ─── Read audio files from a directory handle ─────────────────────────────────
async function readAudioFiles(dir: FileSystemDirectoryHandle): Promise<File[]> {
  const files: File[] = [];
  // @ts-expect-error – values() is available in Chrome 86+
  for await (const entry of dir.values()) {
    if (entry.kind === "file" && AUDIO_EXT.test(entry.name)) {
      const file: File = await (entry as FileSystemFileHandle).getFile();
      files.push(file);
    }
  }
  return files.sort((a, b) => a.name.localeCompare(b.name));
}

// ─── Format seconds as mm:ss ──────────────────────────────────────────────────
function fmt(sec: number): string {
  if (!isFinite(sec)) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ─── Component ────────────────────────────────────────────────────────────────
export function MusicPlayer({ collapsed }: { collapsed: boolean }) {
  const [open,          setOpen]          = useState(false);
  const [tab,           setTab]           = useState<Tab>("synth");
  const [preset,        setPreset]        = useState<Preset>("ambient");
  const [stationId,     setStationId]     = useState("groove");
  const [volume,        setVolume]        = useState(0.38);
  const [playing,       setPlaying]       = useState(false);
  const [generating,    setGenerating]    = useState(false);
  const [radioErr,      setRadioErr]      = useState(false);
  const [radioState,    setRadioState]    = useState<"idle"|"loading"|"live">("idle");

  // Local folder state
  const [playlist,      setPlaylist]      = useState<File[]>([]);
  const [trackIdx,      setTrackIdx]      = useState(0);
  const [shuffleOn,     setShuffleOn]     = useState(false);
  const [folderName,    setFolderName]    = useState("");
  const [needsPerm,     setNeedsPerm]     = useState(false);
  const [trackTime,     setTrackTime]     = useState(0);
  const [trackDur,      setTrackDur]      = useState(0);
  const [scanningDir,   setScanningDir]   = useState(false);

  // Web Audio refs
  const ctxRef    = useRef<AudioContext | null>(null);
  const masterRef = useRef<GainNode | null>(null);
  const padRefs   = useRef<{ osc: OscillatorNode; lfo: OscillatorNode; g: GainNode }[]>([]);
  const audioRef  = useRef<HTMLAudioElement | null>(null);
  const objUrlRef = useRef<string | null>(null);
  const melodyRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const beatRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  const dirRef    = useRef<FileSystemDirectoryHandle | null>(null);
  const playlistRef = useRef<File[]>([]);   // mirror of playlist for callbacks
  const trackIdxRef = useRef(0);
  const shuffleRef  = useRef(false);

  useEffect(() => { playlistRef.current = playlist; }, [playlist]);
  useEffect(() => { trackIdxRef.current = trackIdx; }, [trackIdx]);
  useEffect(() => { shuffleRef.current = shuffleOn; }, [shuffleOn]);

  // ── AudioContext ────────────────────────────────────────────────────────────
  function getCtx(): AudioContext {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext();
      masterRef.current = ctxRef.current.createGain();
      masterRef.current.gain.value = volume;
      masterRef.current.connect(ctxRef.current.destination);
    }
    if (ctxRef.current.state === "suspended") ctxRef.current.resume();
    return ctxRef.current;
  }

  // ── Note / drum helpers ─────────────────────────────────────────────────────
  function note(freq: number, dur: number, type: OscillatorType = "triangle", vol = 0.07, detune = 0) {
    try {
      const ac = getCtx(); const osc = ac.createOscillator(); const g = ac.createGain(); const now = ac.currentTime;
      osc.type = type; osc.frequency.value = freq; osc.detune.value = detune;
      g.gain.setValueAtTime(0, now); g.gain.linearRampToValueAtTime(vol, now + 0.04); g.gain.exponentialRampToValueAtTime(0.001, now + dur);
      osc.connect(g); g.connect(masterRef.current!); osc.start(now); osc.stop(now + dur + 0.06);
    } catch { /**/ }
  }
  function kick(vol = 0.32) {
    try {
      const ac = getCtx(); const osc = ac.createOscillator(); const g = ac.createGain(); const now = ac.currentTime;
      osc.type = "sine"; osc.frequency.setValueAtTime(170, now); osc.frequency.exponentialRampToValueAtTime(48, now + 0.14);
      g.gain.setValueAtTime(vol, now); g.gain.exponentialRampToValueAtTime(0.001, now + 0.30);
      osc.connect(g); g.connect(masterRef.current!); osc.start(now); osc.stop(now + 0.34);
    } catch { /**/ }
  }
  function hihat(vol = 0.09) {
    try {
      const ac = getCtx(); const bufSz = Math.ceil(ac.sampleRate * 0.07);
      const buf = ac.createBuffer(1, bufSz, ac.sampleRate); const data = buf.getChannelData(0);
      for (let i = 0; i < bufSz; i++) data[i] = Math.random() * 2 - 1;
      const src = ac.createBufferSource(); src.buffer = buf;
      const filt = ac.createBiquadFilter(); filt.type = "highpass"; filt.frequency.value = 7800;
      const g = ac.createGain(); const now = ac.currentTime;
      g.gain.setValueAtTime(vol, now); g.gain.exponentialRampToValueAtTime(0.001, now + 0.06);
      src.connect(filt); filt.connect(g); g.connect(masterRef.current!); src.start(now); src.stop(now + 0.08);
    } catch { /**/ }
  }

  // ── Pad / sequencer stop ────────────────────────────────────────────────────
  function stopPad() {
    const ac = ctxRef.current;
    padRefs.current.forEach(({ osc, lfo, g }) => {
      try { if (ac) g.gain.setTargetAtTime(0, ac.currentTime, 0.4); setTimeout(() => { try { osc.stop(); lfo.stop(); } catch { /**/ } }, 600); } catch { /**/ }
    });
    padRefs.current = [];
  }
  function stopSeq() {
    if (melodyRef.current) { clearInterval(melodyRef.current); melodyRef.current = null; }
    if (beatRef.current)   { clearInterval(beatRef.current);   beatRef.current   = null; }
  }

  // ── Audio element stop ──────────────────────────────────────────────────────
  function stopAudioEl() {
    if (audioRef.current) {
      // MUST clear handlers before setting src="" — otherwise onerror fires
      // and triggers the next-track logic, causing unstoppable auto-advance
      audioRef.current.onended      = null;
      audioRef.current.onerror      = null;
      audioRef.current.ontimeupdate = null;
      audioRef.current.oncanplay    = null;
      audioRef.current.onplaying    = null;
      audioRef.current.onwaiting    = null;
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    if (objUrlRef.current) { URL.revokeObjectURL(objUrlRef.current); objUrlRef.current = null; }
    setRadioErr(false); setRadioState("idle");
    setTrackTime(0); setTrackDur(0);
  }

  // ── Pad start ───────────────────────────────────────────────────────────────
  function startPad(freqs: number[], padGain: number, lfoRate: number, attack: number) {
    const ac = getCtx(); const now = ac.currentTime;
    freqs.forEach((freq, i) => {
      const osc = ac.createOscillator(); const lfo = ac.createOscillator(); const lfoG = ac.createGain(); const g = ac.createGain();
      osc.type = i < 3 ? "sine" : "triangle"; osc.frequency.value = freq + i * 0.2;
      lfo.type = "sine"; lfo.frequency.value = lfoRate + i * 0.017; lfoG.gain.value = padGain * 0.22;
      lfo.connect(lfoG); lfoG.connect(g.gain);
      g.gain.setValueAtTime(0, now); g.gain.linearRampToValueAtTime(padGain, now + attack + i * 0.55);
      osc.connect(g); g.connect(masterRef.current!); osc.start(now); lfo.start(now);
      padRefs.current.push({ osc, lfo, g });
    });
  }

  // ── Synth presets ───────────────────────────────────────────────────────────
  function startAmbient() {
    stopPad(); stopSeq(); stopAudioEl();
    startPad(AMBIENT_PAD, 0.08, 0.07, 2.8);
    let i = 0; note(AMBIENT_MELODY[0], 1.9, "triangle", 0.065);
    melodyRef.current = setInterval(() => { i = (i + 1) % AMBIENT_MELODY.length; note(i % 5 === 0 ? AMBIENT_MELODY[i] * 2 : AMBIENT_MELODY[i], 1.9, "triangle", 0.065); }, 2000);
  }
  function startFocus() {
    stopPad(); stopSeq(); stopAudioEl();
    startPad([130.8, 196, 261.6, 392], 0.055, 0.10, 2.0);
    let step = 0; let melStep = 0; kick(0.28); note(FOCUS_BASS[0], 0.65, "triangle", 0.10);
    beatRef.current = setInterval(() => {
      step = (step + 1) % 8;
      if (step === 0 || step === 4) { kick(0.28); note(FOCUS_BASS[step % 4], 0.65, "triangle", 0.10); }
      if (step === 2 || step === 6) { kick(0.14); }
      if (step % 2 === 1) { hihat(0.08 + (step === 3 || step === 7 ? 0.04 : 0)); }
      if (step % 4 === 2) { note(FOCUS_MELODY[melStep % FOCUS_MELODY.length], 0.55, "triangle", 0.065); melStep++; }
    }, 375);
  }
  function startLounge() {
    stopPad(); stopSeq(); stopAudioEl();
    startPad(LOUNGE_PAD, 0.065, 0.09, 3.0);
    let i = 0; note(LOUNGE_BASS[0], 0.55, "triangle", 0.13);
    beatRef.current = setInterval(() => {
      i = (i + 1) % LOUNGE_BASS.length;
      note(LOUNGE_BASS[i], 0.55, "triangle", 0.13);
      if (i % 4 === 3) { note(LOUNGE_PAD[2], 0.35, "sine", 0.045, -8); note(LOUNGE_PAD[3], 0.35, "sine", 0.038, 6); }
    }, 600);
  }
  // Soft recurring bip — the old generation pulse, now a manual play/stop preset.
  function startBip() {
    stopPad(); stopSeq(); stopAudioEl();
    const ping = () => note(185, 0.30, "sine", 0.05);
    ping();
    beatRef.current = setInterval(ping, 1800);
  }

  // ── LOCAL: play a file by index ─────────────────────────────────────────────
  const playTrack = useCallback((files: File[], idx: number) => {
    if (files.length === 0) return;
    const safeIdx = ((idx % files.length) + files.length) % files.length;
    stopPad(); stopSeq();
    // Clear handlers FIRST — setting src="" fires onerror which would re-trigger playTrack
    if (audioRef.current) {
      audioRef.current.onended      = null;
      audioRef.current.onerror      = null;
      audioRef.current.ontimeupdate = null;
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    if (objUrlRef.current) { URL.revokeObjectURL(objUrlRef.current); objUrlRef.current = null; }

    const file = files[safeIdx];
    const url  = URL.createObjectURL(file);
    objUrlRef.current = url;

    const el = new Audio(url);
    el.volume = volume;

    el.ontimeupdate = () => { setTrackTime(el.currentTime); setTrackDur(isFinite(el.duration) ? el.duration : 0); };
    el.onended = () => {
      // Read refs at fire-time, not at playTrack call-time
      const list = playlistRef.current;
      if (list.length === 0) return;
      const cur  = trackIdxRef.current;
      const next = shuffleRef.current
        ? Math.floor(Math.random() * list.length)
        : (cur + 1) % list.length;
      playTrack(list, next);
    };
    el.onerror = () => {
      const list = playlistRef.current;
      if (list.length === 0) return;
      playTrack(list, (trackIdxRef.current + 1) % list.length);
    };

    el.play().catch(() => {});
    audioRef.current = el;
    setTrackIdx(safeIdx);
    setPlaying(true);
    setTab("local");
    setTrackTime(0); setTrackDur(0);
  }, [volume]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── LOCAL: open folder picker ───────────────────────────────────────────────
  async function pickFolder() {
    if (!("showDirectoryPicker" in window)) {
      alert("Your browser does not support folder picking. Please use Chrome or Edge.");
      return;
    }
    try {
      // @ts-expect-error – File System Access API
      const dir: FileSystemDirectoryHandle = await window.showDirectoryPicker({ mode: "read" });
      setScanningDir(true);
      await saveHandle(dir);
      dirRef.current = dir;
      const files = await readAudioFiles(dir);
      setPlaylist(files);
      setFolderName(dir.name);
      setNeedsPerm(false);
      setScanningDir(false);
      if (files.length > 0) playTrack(files, 0);
    } catch (e) {
      setScanningDir(false);
      if ((e as Error).name !== "AbortError") console.error(e);
    }
  }

  // ── LOCAL: re-grant permission after page reload ────────────────────────────
  async function regrantPermission() {
    const dir = dirRef.current;
    if (!dir) return;
    try {
      // @ts-expect-error – File System Access API
      const result = await dir.requestPermission({ mode: "read" });
      if (result === "granted") {
        setScanningDir(true);
        const files = await readAudioFiles(dir);
        setPlaylist(files);
        setNeedsPerm(false);
        setScanningDir(false);
        if (files.length > 0) playTrack(files, 0);
      }
    } catch { /**/ }
  }

  // ── LOCAL: restore folder from IndexedDB on mount ───────────────────────────
  useEffect(() => {
    loadHandle().then(async (handle) => {
      if (!handle) return;
      dirRef.current = handle;
      setFolderName(handle.name);
      try {
        // @ts-expect-error – File System Access API
        const perm: string = await handle.queryPermission({ mode: "read" });
        if (perm === "granted") {
          const files = await readAudioFiles(handle);
          setPlaylist(files);
        } else {
          setNeedsPerm(true);
        }
      } catch { setNeedsPerm(true); }
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Radio ───────────────────────────────────────────────────────────────────
  function startRadio(sid: string) {
    stopPad(); stopSeq(); stopAudioEl();
    setRadioErr(false); setRadioState("loading");
    const station = STATIONS.find(s => s.id === sid) ?? STATIONS[0];
    const el = new Audio(); el.volume = volume; el.src = station.url;
    el.oncanplay = () => setRadioState("live"); el.onplaying = () => setRadioState("live");
    el.onerror = () => { setRadioErr(true); setRadioState("idle"); };
    el.onwaiting = () => setRadioState("loading");
    el.play().catch(() => { setRadioErr(true); setRadioState("idle"); });
    audioRef.current = el;
  }

  // ── Volume ──────────────────────────────────────────────────────────────────
  function handleVolume(v: number) {
    setVolume(v);
    if (masterRef.current && ctxRef.current) masterRef.current.gain.setTargetAtTime(v, ctxRef.current.currentTime, 0.05);
    if (audioRef.current) audioRef.current.volume = v;
  }

  // ── Play / Stop ─────────────────────────────────────────────────────────────
  function play(nextTab?: Tab, nextPreset?: Preset, nextSid?: string) {
    const t = nextTab ?? tab; const p = nextPreset ?? preset; const s = nextSid ?? stationId;
    if (t === "synth") {
      if (p === "ambient") startAmbient();
      else if (p === "focus") startFocus();
      else if (p === "lounge") startLounge();
      else startBip();
      setPreset(p);
    } else if (t === "local") {
      playTrack(playlistRef.current, trackIdxRef.current);
    } else {
      startRadio(s); setStationId(s);
    }
    setTab(t); setPlaying(true);
  }
  function stop() { stopPad(); stopSeq(); stopAudioEl(); setPlaying(false); }

  // ── Seek ────────────────────────────────────────────────────────────────────
  function handleSeek(v: number) {
    if (audioRef.current && isFinite(audioRef.current.duration)) {
      audioRef.current.currentTime = v * audioRef.current.duration;
    }
  }

  useEffect(() => {
    function handler(e: Event) {
      const active = (e as CustomEvent<{ active: boolean }>).detail.active;
      // No auto ambient or pulse during generation — only update the visual
      // indicator. The bip is now a manual synth preset (play/stop).
      setGenerating(active);
    }
    window.addEventListener("pm-studio:generating", handler);
    return () => window.removeEventListener("pm-studio:generating", handler);
  }, []);

  useEffect(() => () => { stopPad(); stopSeq(); stopAudioEl(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Derived ─────────────────────────────────────────────────────────────────
  const currentFile   = playlist[trackIdx];
  const trackName     = currentFile ? currentFile.name.replace(AUDIO_EXT, "") : "";
  const progressPct   = trackDur > 0 ? trackTime / trackDur : 0;

  // ── Collapsed sidebar ────────────────────────────────────────────────────────
  if (collapsed) {
    return (
      <div className="flex items-center justify-center border-t border-gray-800 py-3">
        <button onClick={() => setOpen(true)} title={playing ? trackName || "Playing" : "Focus music"}
          className="relative flex h-8 w-8 items-center justify-center rounded-md text-gray-500 hover:bg-gray-800 hover:text-gray-200 transition-colors">
          <i className={`ti ti-music text-[17px] ${playing ? "text-indigo-400" : ""}`} aria-hidden />
          {playing    && <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />}
          {generating && <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-amber-400 animate-ping" />}
        </button>
      </div>
    );
  }

  // ── Expanded sidebar ──────────────────────────────────────────────────────────
  return (
    <div className="border-t border-gray-800 shrink-0">

      {/* Header */}
      <button onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-900/40 transition-colors">
        <span className="flex items-center gap-2 text-xs font-medium text-gray-500 min-w-0">
          <i className={`ti ti-music text-sm shrink-0 ${playing ? "text-indigo-400" : ""}`} aria-hidden />
          <span className="truncate">
            {playing && tab === "local" && trackName
              ? trackName
              : playing && tab === "radio"
                ? STATIONS.find(s => s.id === stationId)?.name
                : playing
                  ? `${PRESETS[preset as Preset]?.label ?? ""} — ${PRESETS[preset as Preset]?.desc ?? ""}`
                  : "Focus music"}
          </span>
          {playing    && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500 animate-pulse" />}
          {generating && <span className="shrink-0 rounded px-1 py-0.5 text-[9px] font-bold text-amber-400 border border-amber-800/40 bg-amber-950/30 animate-pulse">AI</span>}
        </span>
        <i className={`ti ${open ? "ti-chevron-down" : "ti-chevron-up"} text-xs text-gray-600 shrink-0`} aria-hidden />
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2.5">

          {/* Tab switcher — 3 tabs */}
          <div className="flex rounded-md border border-gray-800 p-0.5 text-[10px] font-medium">
            {(["synth", "local", "radio"] as Tab[]).map(t => (
              <button key={t} onClick={() => setTab(t)}
                className={`flex-1 rounded py-1 transition-colors ${tab === t ? "bg-gray-700 text-white" : "text-gray-500 hover:text-gray-300"}`}>
                {t === "synth" ? "♫ Synth" : t === "local" ? "📁 Local" : "📻 Radio"}
              </button>
            ))}
          </div>

          {/* ── SYNTH TAB ── */}
          {tab === "synth" && (
            <div className="grid grid-cols-2 gap-1">
              {(Object.keys(PRESETS) as Preset[]).map(p => {
                const active = preset === p && playing && tab === "synth";
                return (
                  <button key={p} onClick={() => play("synth", p)}
                    className={`flex flex-col items-center gap-0.5 rounded-md border py-2 text-[10px] font-medium transition-all ${
                      active ? "border-indigo-600/70 bg-indigo-950/40 text-indigo-300"
                             : "border-gray-800 bg-gray-900/30 text-gray-500 hover:border-gray-600 hover:text-gray-200"}`}>
                    <i className={`ti ${PRESETS[p].icon} text-sm`} aria-hidden />
                    <span>{PRESETS[p].label}</span>
                    <span className="text-[9px] text-gray-600 leading-none">{PRESETS[p].desc}</span>
                    {active && (
                      <span className="mt-0.5 flex gap-0.5 items-end h-2.5">
                        {[1,2,3].map(b => (
                          <span key={b} className="w-0.5 rounded-sm bg-indigo-400"
                            style={{ height: "100%", animation: `eqBar ${0.5 + b * 0.18}s ease-in-out infinite alternate` }} />
                        ))}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {/* ── LOCAL TAB ── */}
          {tab === "local" && (
            <div className="space-y-2">

              {/* No folder yet */}
              {!folderName && (
                <button onClick={() => void pickFolder()}
                  disabled={scanningDir}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-gray-700 py-4 text-xs text-gray-400 hover:border-indigo-700 hover:text-indigo-300 transition-colors disabled:opacity-50">
                  {scanningDir
                    ? <><i className="ti ti-loader-2 animate-spin" aria-hidden /> Scanning folder…</>
                    : <><i className="ti ti-folder-open text-base" aria-hidden /> Open music folder</>}
                </button>
              )}

              {/* Folder loaded but needs permission re-grant */}
              {folderName && needsPerm && (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5 text-[11px] text-amber-400">
                    <i className="ti ti-lock text-sm" aria-hidden />
                    <span className="truncate font-medium">{folderName}</span>
                  </div>
                  <button onClick={() => void regrantPermission()}
                    className="flex w-full items-center justify-center gap-1.5 rounded-md border border-amber-700/50 bg-amber-950/20 py-1.5 text-[11px] text-amber-300 hover:bg-amber-950/40 transition-colors">
                    <i className="ti ti-lock-open text-xs" aria-hidden /> Allow access to folder
                  </button>
                  <button onClick={() => void pickFolder()}
                    className="flex w-full items-center justify-center gap-1.5 rounded-md border border-gray-700 py-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors">
                    <i className="ti ti-folder-open text-xs" aria-hidden /> Pick different folder
                  </button>
                </div>
              )}

              {/* Folder loaded and permission OK */}
              {folderName && !needsPerm && (
                <>
                  {/* Folder name + change button */}
                  <div className="flex items-center justify-between gap-1">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <i className="ti ti-folder text-xs text-indigo-400 shrink-0" aria-hidden />
                      <span className="truncate text-[11px] font-medium text-gray-300">{folderName}</span>
                    </div>
                    <button onClick={() => void pickFolder()}
                      className="shrink-0 flex items-center gap-1 rounded border border-gray-700 bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-400 hover:border-gray-500 hover:text-white transition-colors">
                      <i className="ti ti-folder-open text-xs" aria-hidden />
                      Change
                    </button>
                  </div>

                  {/* No audio files */}
                  {playlist.length === 0 && !scanningDir && (
                    <p className="text-center text-[10px] text-gray-600 py-2">
                      No audio files found in this folder.<br />
                      Supported: mp3, flac, wav, ogg, m4a, aac
                    </p>
                  )}

                  {/* Playlist */}
                  {playlist.length > 0 && (
                    <>
                      {/* Now playing */}
                      {playing && tab === "local" && currentFile && (
                        <div className="rounded-md border border-indigo-800/40 bg-indigo-950/20 px-2.5 py-1.5">
                          <p className="text-[10px] text-indigo-400 leading-none mb-0.5">Now playing</p>
                          <p className="text-[11px] font-medium text-white truncate">{trackName}</p>
                          {/* Progress bar */}
                          <div className="mt-1.5 flex items-center gap-1.5">
                            <span className="text-[9px] text-gray-600 tabular-nums w-6 shrink-0">{fmt(trackTime)}</span>
                            <div className="flex-1 h-1 bg-gray-800 rounded-full overflow-hidden cursor-pointer"
                              onClick={e => {
                                const rect = (e.target as HTMLElement).getBoundingClientRect();
                                handleSeek((e.clientX - rect.left) / rect.width);
                              }}>
                              <div className="h-full bg-indigo-500 rounded-full transition-all"
                                style={{ width: `${progressPct * 100}%` }} />
                            </div>
                            <span className="text-[9px] text-gray-600 tabular-nums w-6 shrink-0 text-right">{fmt(trackDur)}</span>
                          </div>
                        </div>
                      )}

                      {/* Song list */}
                      <div className="max-h-32 overflow-y-auto space-y-0.5 rounded-md border border-gray-800">
                        {playlist.map((f, i) => (
                          <button key={f.name + i}
                            onClick={() => playTrack(playlist, i)}
                            className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[10px] transition-colors ${
                              i === trackIdx && playing && tab === "local"
                                ? "bg-indigo-950/30 text-indigo-300"
                                : "text-gray-400 hover:bg-gray-800/60 hover:text-gray-200"
                            }`}>
                            {i === trackIdx && playing && tab === "local"
                              ? <i className="ti ti-volume text-xs text-indigo-400 shrink-0" aria-hidden />
                              : <span className="w-3 shrink-0 text-[9px] text-gray-700 tabular-nums">{i + 1}</span>}
                            <span className="truncate">{f.name.replace(AUDIO_EXT, "")}</span>
                          </button>
                        ))}
                      </div>

                      <p className="text-[9px] text-gray-700 px-0.5">{playlist.length} tracks · local only · zero internet</p>
                    </>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── RADIO TAB ── */}
          {tab === "radio" && (
            <div className="space-y-1">
              {STATIONS.map(s => {
                const active = stationId === s.id && playing && tab === "radio";
                return (
                  <button key={s.id} onClick={() => { setStationId(s.id); play("radio", undefined, s.id); }}
                    className={`flex w-full items-center justify-between rounded-md border px-2.5 py-1.5 text-left transition-all ${
                      active ? "border-indigo-700/50 bg-indigo-950/25 text-indigo-300"
                             : "border-gray-800 bg-gray-900/20 text-gray-400 hover:border-gray-700 hover:text-gray-200"}`}>
                    <div className="min-w-0">
                      <p className="text-[11px] font-medium leading-none truncate">{s.name}</p>
                      <p className="mt-0.5 text-[10px] text-gray-600">{s.genre} · 64 kbps</p>
                    </div>
                    {active && (
                      radioState === "loading"
                        ? <i className="ti ti-loader-2 animate-spin text-xs text-indigo-400 shrink-0" aria-hidden />
                        : <span className="flex gap-0.5 items-end h-3 shrink-0">
                            {[1,2,3].map(b => (
                              <span key={b} className="w-0.5 rounded-sm bg-indigo-400"
                                style={{ height: `${30 + b * 20}%`, animation: `eqBar ${0.55 + b * 0.16}s ease-in-out infinite alternate` }} />
                            ))}
                          </span>
                    )}
                  </button>
                );
              })}
              {radioErr && <p className="text-[10px] text-red-400 px-1">Stream unavailable — try another station.</p>}
              <p className="text-[9px] text-gray-700 px-1 pt-0.5">SomaFM · free · ~28 MB/hr · browser streams direct</p>
            </div>
          )}

          {/* ── Transport controls (synth: play/stop; local: prev/play/next/shuffle) ── */}
          <div className="space-y-2">
            {tab === "local" && playlist.length > 0 ? (
              <div className="space-y-1.5">
                {/* Row 1: Prev / Play-Pause / Next */}
                <div className="flex items-stretch gap-1.5">
                  <button
                    onClick={() => { const prev = trackIdx === 0 ? playlist.length - 1 : trackIdx - 1; playTrack(playlist, prev); }}
                    className="flex flex-1 flex-col items-center justify-center gap-0.5 rounded-md border border-gray-600 bg-gray-800 py-2 text-gray-200 hover:bg-gray-700 hover:border-gray-500 transition-colors"
                  >
                    <span className="text-base leading-none">⏮</span>
                    <span className="text-[9px] text-gray-400">Prev</span>
                  </button>

                  <button
                    onClick={() => {
                      if (playing && tab === "local") {
                        // Pause — keep audio element alive so we can resume
                        audioRef.current?.pause();
                        setPlaying(false);
                      } else if (tab === "local" && audioRef.current) {
                        // Resume from exact paused position — don't recreate
                        audioRef.current.play().catch(() => {});
                        setPlaying(true);
                      } else {
                        // Fresh start (e.g. after Stop)
                        playTrack(playlistRef.current, trackIdxRef.current);
                      }
                    }}
                    className={`flex flex-[2] flex-col items-center justify-center gap-0.5 rounded-md border py-2 font-medium transition-colors ${
                      playing && tab === "local"
                        ? "border-amber-700/60 bg-amber-950/30 text-amber-200 hover:bg-amber-950/50"
                        : "border-indigo-600/60 bg-indigo-950/30 text-indigo-200 hover:bg-indigo-950/50"
                    }`}
                  >
                    <span className="text-base leading-none">{playing && tab === "local" ? "⏸" : "▶"}</span>
                    <span className="text-[9px]">{playing && tab === "local" ? "Pause" : "Play"}</span>
                  </button>

                  <button
                    onClick={() => { const next = shuffleOn ? Math.floor(Math.random() * playlist.length) : (trackIdx + 1) % playlist.length; playTrack(playlist, next); }}
                    className="flex flex-1 flex-col items-center justify-center gap-0.5 rounded-md border border-gray-600 bg-gray-800 py-2 text-gray-200 hover:bg-gray-700 hover:border-gray-500 transition-colors"
                  >
                    <span className="text-base leading-none">⏭</span>
                    <span className="text-[9px] text-gray-400">Next</span>
                  </button>
                </div>

                {/* Row 2: Stop + Shuffle */}
                <div className="flex items-stretch gap-1.5">
                  <button
                    onClick={stop}
                    className="flex flex-1 flex-col items-center justify-center gap-0.5 rounded-md border border-gray-600 bg-gray-800 py-1.5 text-gray-200 hover:bg-red-950/40 hover:border-red-800/50 hover:text-red-300 transition-colors"
                  >
                    <span className="text-sm leading-none">⏹</span>
                    <span className="text-[9px] text-gray-400">Stop</span>
                  </button>

                  <button
                    onClick={() => setShuffleOn(s => !s)}
                    className={`flex flex-1 flex-col items-center justify-center gap-0.5 rounded-md border py-1.5 transition-colors ${
                      shuffleOn
                        ? "border-indigo-600/60 bg-indigo-950/30 text-indigo-200"
                        : "border-gray-600 bg-gray-800 text-gray-400 hover:text-gray-200 hover:border-gray-500"
                    }`}
                  >
                    <span className="text-sm leading-none">🔀</span>
                    <span className="text-[9px]">{shuffleOn ? "On" : "Shuffle"}</span>
                  </button>
                </div>
              </div>
            ) : (
              <button onClick={() => playing && tab !== "local" ? stop() : play()}
                className={`flex w-full items-center justify-center gap-1.5 rounded-md border py-1.5 text-[11px] font-medium transition-colors ${
                  playing && tab !== "local"
                    ? "border-gray-700 text-gray-300 hover:bg-gray-800"
                    : "border-indigo-700/50 bg-indigo-950/20 text-indigo-300 hover:bg-indigo-950/40"}`}>
                <span>{playing && tab !== "local" ? "⏹" : "▶"}</span>
                {playing && tab !== "local" ? "Stop" : "Play"}
              </button>
            )}

            {/* Volume */}
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-gray-600 shrink-0 select-none">🔈</span>
              <input type="range" min={0} max={1} step={0.02} value={volume}
                onChange={e => handleVolume(Number(e.target.value))}
                className="flex-1 h-1 accent-indigo-500 cursor-pointer" />
              <span className="text-[11px] text-gray-400 shrink-0 select-none">🔊</span>
            </div>
          </div>

          {/* Generating indicator */}
          {generating && (
            <div className="flex items-center gap-2 rounded-md border border-amber-800/30 bg-amber-950/20 px-2.5 py-1.5">
              <span className="flex gap-0.5 items-end h-3">
                {[0,1,2].map(i => (
                  <span key={i} className="w-0.5 rounded-sm bg-amber-400"
                    style={{ height: "100%", animation: `eqBar ${0.6 + i * 0.18}s ease-in-out ${i * 0.12}s infinite alternate` }} />
                ))}
              </span>
              <span className="text-[10px] text-amber-400">AI generating…</span>
            </div>
          )}

        </div>
      )}

      <style>{`
        @keyframes eqBar {
          from { transform: scaleY(0.25); }
          to   { transform: scaleY(1.0); }
        }
      `}</style>
    </div>
  );
}
