/* global React */
const { useState, useEffect, useRef } = React;

const MESSAGE = "Sorry folks, Chip's closed. Moose out front shoulda told ya.";
const MEME_TOP = "SORRY FOLKS, CHIP'S CLOSED";
const MEME_BOTTOM = "MOOSE OUT FRONT SHOULDA TOLD YA";

function useTypewriter(text, { speed = 55, hold = 2200, restart = true } = {}) {
  const [i, setI] = useState(0);
  const [phase, setPhase] = useState("typing");
  useEffect(() => {
    let t;
    if (phase === "typing") {
      if (i < text.length) {
        t = setTimeout(() => setI(i + 1), speed);
      } else {
        setPhase("holding");
      }
    } else if (phase === "holding") {
      t = setTimeout(() => {
        if (restart) { setI(0); setPhase("typing"); } else { setPhase("done"); }
      }, hold + 2800);
    }
    return () => clearTimeout(t);
  }, [i, phase, text, speed, hold, restart]);
  return { shown: text.slice(0, i), done: phase !== "typing" };
}

function RecTicker() {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setT((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const mm = String(Math.floor(t / 60)).padStart(2, "0");
  const ss = String(t % 60).padStart(2, "0");
  return (
    <div className="rec">
      <span className="rec-dot" />
      <span className="rec-label">REC</span>
      <span className="rec-time">00:{mm}:{ss}</span>
    </div>
  );
}

function Scanlines() {
  return <div className="scanlines" aria-hidden="true" />;
}

function Photo({ className = "" }) {
  return (
    <div className={`photo ${className}`}>
      <img src="assets/guard.jpeg" alt="A confused security guard" />
      <Scanlines />
      <div className="vignette" aria-hidden="true" />
      <RecTicker />
      <div className="tape-meta">
        <span>CH-04</span>
        <span>·</span>
        <span>SP</span>
        <span>·</span>
        <span>EP</span>
      </div>
      <div className="meme meme-top">{MEME_TOP}</div>
      <div className="meme meme-bottom">{MEME_BOTTOM}</div>
    </div>
  );
}

function TypedLine() {
  const { shown, done } = useTypewriter(MESSAGE);
  const idx = MESSAGE.indexOf("Chip's");
  const hasChip = shown.length >= idx + "Chip's".length;
  const before = hasChip ? shown.slice(0, idx) : shown.slice(0, Math.min(shown.length, idx));
  const chip = hasChip ? "Chip's" : (shown.length > idx ? shown.slice(idx) : "");
  const after = hasChip ? shown.slice(idx + "Chip's".length) : "";
  return (
    <p className="typed">
      <span className="quote-mark">“</span>
      {before}
      <span className="hl">{chip}</span>
      {after}
      <span className={`caret ${done ? "blink" : ""}`}>▍</span>
      {done && shown.length === MESSAGE.length ? <span className="quote-mark closing">”</span> : null}
    </p>
  );
}

function Buttons({ onWake }) {
  return (
    <div className="cta-row">
      <button type="button" className="cta cta-alt" onClick={onWake}>
        <span className="cta-emoji" aria-hidden="true">⏰</span>
        <span className="cta-label">Wake up the admin</span>
      </button>
    </div>
  );
}

function SentDialog({ open, onClose }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-icon" aria-hidden="true">⏰</div>
        <div className="modal-title">Sent!</div>
        <div className="modal-body">
          We rang the admin. They're presumably looking for the moose.
        </div>
        <button type="button" className="modal-close" onClick={onClose}>OK</button>
      </div>
    </div>
  );
}

function Scene({ variant }) {
  const [sent, setSent] = useState(false);
  return (
    <div className={`scene scene-${variant}`}>
      <Photo />
      <div className="panel">
        <div className="eyebrow">
          <span className="eyebrow-block" />
          <span>Error · four · zero · four</span>
        </div>
        <h1 className="page-num">
          <span className="d">4</span>
          <span className="d zero">0</span>
          <span className="d">4</span>
        </h1>
        <p className="blurb">
          Chip Leader auto-updates during the live tournament, Thursday to Sunday. Otherwise you'll see the most recent stats. If you're seeing this page, something went wrong. The admin has been notified. If it's something serious, click the button:
        </p>
        <Buttons onWake={() => setSent(true)} />
        <div className="signoff">chip-leader, an ogrady joint</div>
      </div>
      <SentDialog open={sent} onClose={() => setSent(false)} />
    </div>
  );
}

window.Scene = Scene;
