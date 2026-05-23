# Handoff: Chip Leader 404 Page

## Overview
A custom 404 / error page for **Chip Leader** (an ogrady joint). The page leans into the *National Lampoon's Vacation* "Sorry folks, park's closed" gag — a confused security-guard photo with white meme-caption text, a big bold 404, a short explainer about Chip Leader's tournament schedule, and a single action button ("⏰ Wake up the admin") that pops a "Sent!" confirmation modal. Used whenever a route doesn't resolve or the underlying stats endpoint is unreachable.

## About the Design Files
The files in this bundle are **design references created in HTML** — a prototype showing intended look and behavior, not production code to copy directly. The task is to **recreate this design in Chip Leader's existing codebase** (use its current framework, routing, component patterns, and design tokens). If Chip Leader is not yet on a framework, React is a reasonable default given the prototype is written in JSX.

The HTML prototype uses Babel-in-the-browser, Google Fonts, and a "design canvas" wrapper that shows desktop + mobile artboards side-by-side. None of that scaffolding should ship — only the **Scene** itself (the 404 page) and its assets.

## Fidelity
**High-fidelity.** Exact colors, type, spacing, and animation timings are specified below. Reproduce pixel-for-pixel within the constraints of the target codebase's styling system.

## Screens / Views

There is **one screen** with two **responsive variants**: desktop (1440×900) and mobile (390×844). The same component tree drives both — only sizing/layout differs.

### Layout

**Desktop (≥768px or per existing breakpoints):**
- Two-column CSS grid, `1fr 1fr`, full viewport height (page is fixed-height in the prototype but in production should be `min-height: 100vh`).
- Left column: photo (full-bleed, `object-fit: cover`), 1px solid `--ink` right border.
- Right column: content panel, 64px top/bottom padding, 72px left/right padding, vertical flex with `gap: 32px`.

**Mobile (<768px):**
- Single column, vertical stack.
- Photo on top, fixed height 340px, 1px solid `--ink` bottom border.
- Panel below: padding `28px 24px 32px`, vertical flex with `gap: 18px`.
- Buttons stack full-width.

### Panel content (top to bottom)

1. **Eyebrow** — small caps line: a 22×10px red block, then text "Error · four · zero · four".
   - Desktop: 13px, mobile: 10px. `letter-spacing: 0.18em`, `text-transform: uppercase`, color `--ink-soft`.
2. **404 numeral** — display heading.
   - Font: Bowlby One, 400 weight.
   - Desktop: 280px, mobile: 128px. `line-height: 0.85`, `letter-spacing: -0.04em`.
   - The middle **0** is colored `--accent` (red) and runs a subtle "jiggle" animation every 4s (rotates -3° → 3° → 0 over the last ~12% of the cycle).
3. **Blurb** — DM Mono, color `--ink-soft`, `max-width: 56ch`, `text-wrap: pretty`.
   - Desktop: 16px / 1.55 line-height. Mobile: 12px / 1.5.
   - Copy (verbatim):
     > Chip Leader auto-updates during the live tournament, Thursday to Sunday. Otherwise you'll see the most recent stats. If you're seeing this page, something went wrong. The admin has been notified. If it's something serious, click the button:
4. **CTA row** — single button (see below). On desktop it's auto-width inline; on mobile it stretches full-width and the row becomes a vertical stack.
5. **Signoff** — single line: a small 8×8px red square, then "chip-leader, an ogrady joint".
   - DM Mono, desktop 13px / mobile 11px. Color `--ink-soft`. 1px dashed top border (`--rule`), 18px top padding. `margin-top: auto` so it pins to the bottom of the panel.

### Photo overlays

The guard photo (`assets/guard.jpeg`) has several layered overlays:

- **Scanlines** — repeating linear gradient, 4px cycle, `mix-blend-mode: multiply`, ~18% opacity dark bands. Adds CRT/VHS feel.
- **Vignette** — radial gradient, transparent at 55% to `rgba(0,0,0,0.55)` at the edges.
- **REC indicator** (top-left of photo): red dot (10px, blinks every 1.2s via `steps(2)` animation), "REC" label, and a running mm:ss timer that increments once per second from page load. DM Mono 13px, white, with dark text-shadow. Mobile: 11px, 8px dot.
- **Tape meta** (top-right of photo): "CH-04 · SP · EP". DM Mono 12px (mobile 10px), white, opacity 0.85.
- **Meme captions** — classic white Impact with thick black stroke, all-caps:
  - Top: "SORRY FOLKS, CHIP'S CLOSED" at `top: 5%`.
  - Bottom: "MOOSE OUT FRONT SHOULDA TOLD YA" at `bottom: 5%`.
  - Desktop 64px, mobile 28px. Font stack: `Impact, 'Haettenschweiler', 'Arial Narrow Bold', 'Oswald', sans-serif`.
  - Stroke is faked with 8-direction black `text-shadow` (2–3px offsets) so it renders consistently across browsers; `paint-order: stroke fill` + `-webkit-text-stroke: 2px #000` as a secondary layer if you prefer.
  - Pop-in animation: scale `0.5 → 1.08 → 1` with slight rotation, `cubic-bezier(0.34, 1.56, 0.64, 1)` easing, 0.55s duration. Top caption animates with 0.35s delay, bottom with 1.1s delay.
- The base `<img>` itself is rendered with `filter: saturate(0.9) contrast(1.05) brightness(0.95)`.

### "Wake up the admin" button

- Label: `⏰ Wake up the admin`
- Background: `--paper` (cream), text `--ink` (near-black), 2px solid `--ink` border.
- Offset shadow effect: a `::after` pseudo-element (`--moss` green) translated 6px right + 6px down, behind the button. On hover, the button itself translates +2/+2 and the shadow shrinks to +4/+4 — creates the classic brutalist "press in" effect. 0.15s ease transitions.
- Padding: desktop 18px 28px / 15px font; mobile 14px 18px / 12px font.
- DM Mono 500 weight, `letter-spacing: 0.04em`.
- The ⏰ emoji wiggles every ~2.4s (rotation keyframe, `transform-origin: 50% 40%`).
- Mobile button is full-width and centered (`justify-content: center`).

### "Sent!" modal

Triggered by clicking the Wake up button. Closes on:
- Click of the OK button
- Click on the scrim
- Escape key

Structure:
- **Scrim** — full-bleed (relative to the scene container, not the viewport — see "Implementation notes" below), `rgba(20, 14, 10, 0.55)`, `backdrop-filter: blur(2px)`. Fades in 0.18s.
- **Modal box** — `--paper` background, 2px solid `--ink` border, 8px×8px solid `--accent` offset shadow, centered. `width: min(420px, 86%)`, padding `32px 32px 24px`, centered text. Spring entry: `translateY(8px) scale(0.92) → translateY(0) scale(1)` with `cubic-bezier(0.34, 1.56, 0.64, 1)`, 0.32s.
- **Icon** — large ⏰ emoji (44px line-height), same wiggle animation as the button (faster: 1.4s cycle).
- **Title** — "Sent!" in Bowlby One, 36px (mobile 30px), `letter-spacing: -0.01em`.
- **Body** — Instrument Serif *italic*, 18px (mobile 16px), color `--ink-soft`:
  > We rang the admin. They're presumably looking for the moose.
- **Close button** — "OK", 2px solid `--ink`, ink background, paper text, DM Mono 13px. Hover: switches background + border to `--accent`.

## Interactions & Behavior

| Trigger | Behavior |
| --- | --- |
| Page load | Photo overlays render immediately. Top meme caption pops in at 0.35s, bottom at 1.1s. REC dot starts blinking; timer starts counting. Middle "0" of the 404 begins its jiggle loop. |
| Click "Wake up the admin" | Open modal (`sent = true`). In production this should also fire a request to whatever endpoint pings the admin (Slack webhook, PagerDuty, email, etc. — coordinate with backend). |
| Click OK / scrim / Escape | Close modal (`sent = false`). |
| Hover any button | Translate +2/+2, shadow shrinks. |

There is no router-level navigation from this page — it's intentionally a dead-end with one action. If product wants a "back to home" link later, add it but the current spec is single-button.

## State Management

Single boolean per scene: `sent: bool` — controls modal visibility. That's it. The recording timer is local component state (`useState` + `setInterval`), reset on unmount.

In a real codebase, also wire:
- The "wake up the admin" action to your real notification channel.
- An optional `?reason=` query param or referrer log on the page so the admin notification carries some context about which route 404'd.

## Design Tokens

All defined as CSS custom properties on `.scene` in `scene.css`. Map these into your codebase's existing token system (Tailwind config, CSS variables, theme object, etc.).

| Token | Value | Usage |
| --- | --- | --- |
| `--paper` | `#efe6d2` | Page background, button text on dark CTAs |
| `--paper-deep` | `#e3d6b3` | (Reserved — unused currently) |
| `--ink` | `#1a1410` | Primary text, button backgrounds, borders |
| `--ink-soft` | `#4a3e30` | Secondary text, eyebrow, blurb |
| `--accent` | `#c83a1d` | The "0", eyebrow block, REC dot, signoff square, modal shadow |
| `--moss` | `#2f4a2a` | Offset shadow on Wake-up button |
| `--rule` | `rgba(26, 20, 16, 0.18)` | Dashed top border of the signoff |

**Page background grain** (behind the scene): two stacked `radial-gradient` dot patterns at 3px and 7px grids, low opacity, `mix-blend-mode: multiply`. Plus a 28px horizontal hairline rule pattern over the top. Both decorative — drop them if the host app's style budget doesn't allow extra pseudo-element layers.

**Spacing**: 4 / 8 / 14 / 18 / 22 / 28 / 32 / 64 / 72 px. Nothing exotic.

**Border radius**: **0** everywhere. Intentional — this is brutalist/print-feeling, no rounded corners. Don't add any.

**Typography**:

| Family | Where | Size (desktop / mobile) |
| --- | --- | --- |
| **Bowlby One** (400) | "404" numeral, "Sent!" modal title | 280px / 128px ; 36px / 30px |
| **Instrument Serif** italic (400) | Modal body | 18px / 16px |
| **DM Mono** (400/500) | Eyebrow, blurb, REC, tape meta, buttons, signoff | 10–16px |
| **Impact** (system) | Meme captions on photo | 64px / 28px |

Load Bowlby One, Instrument Serif (italic), and DM Mono from Google Fonts. Impact is system; the fallback stack is in `scene.css`.

## Animations

| Name | Selector | Duration / Easing | Loops |
| --- | --- | --- | --- |
| `rec-blink` | `.rec-dot` | 1.2s `steps(2)` | infinite |
| `jiggle` | `.page-num .zero` | 4s ease-in-out | infinite, fires in last ~12% |
| `meme-pop` | `.meme` | 0.55s `cubic-bezier(0.34, 1.56, 0.64, 1)` | once (top 0.35s delay, bottom 1.1s) |
| `alarm-wiggle` | `.cta-alt .cta-emoji`, `.modal-icon` | 2.4s / 1.4s ease-in-out | infinite |
| `scrim-in` | `.modal-scrim` | 0.18s ease-out | once |
| `modal-in` | `.modal` | 0.32s `cubic-bezier(0.34, 1.56, 0.64, 1)` | once |
| Button press | `.cta:hover` | 0.15s ease | hover state |

Respect `prefers-reduced-motion` — if the host app already has a motion guard, gate the infinite-loop animations (REC blink, jiggle, alarm-wiggle) behind it.

## Assets

- `assets/guard.jpeg` — the security-guard photograph. **Confirm rights/licensing before shipping.** It's recognizably a meme image (the *National Lampoon's Vacation* riff); if Chip Leader is a public product, either license it, get express permission, or commission an original photo in the same vein. The design works with any squarish portrait of someone looking nonplussed in a uniform.
- No icons — the alarm ⏰ is the Unicode emoji, rendered by the OS. If the host app uses a custom emoji font (Twemoji etc.), it will pick that up automatically. The brutalist look of the design lets system emoji read fine.

## Implementation notes / gotchas

- **The "scene" is a positioned container.** The modal scrim uses `position: absolute; inset: 0;` relative to `.scene`, not the viewport — because in the prototype each variant is a fixed-size artboard. In production, switch `.modal-scrim` to `position: fixed` (or use your existing portal/dialog primitive) so it overlays the whole window.
- **Don't ship the design-canvas wrapper.** `design-canvas.jsx` and the `<DesignCanvas>` / `<DCSection>` / `<DCArtboard>` markup in `404 - Chip's Closed.html` only exist to show desktop + mobile side-by-side in review. Render `<Scene />` directly as the page.
- **Drop the `scene-desktop` / `scene-mobile` variant classes.** In `scene.css` they're tied to fixed pixel sizes (1440×900 / 390×844). In production, replace those with media queries / your existing breakpoint mixin. The token values (font sizes, paddings) all transfer cleanly.
- **Accessibility**:
  - The modal needs a real `role="dialog"`, `aria-modal="true"`, focus trapping, and focus return-to-trigger — the prototype only has the role attribute. Use the host app's existing dialog primitive (Radix, Headless UI, your own) rather than re-implementing.
  - The photo's `alt` is currently "A confused security guard" — tune to the host's voice.
  - The REC blinking dot and meme-pop should be paused under `prefers-reduced-motion: reduce`.
- **Browser support**: `backdrop-filter` on the scrim is progressive enhancement; the dark overlay alone works without it. `-webkit-text-stroke` + the multi-direction text-shadow combo on `.meme` is intentional belt-and-suspenders for the Impact stroke effect across browsers.

## Files in this bundle

| File | Purpose |
| --- | --- |
| `README.md` | This document. |
| `404 - Chip's Closed.html` | Top-level prototype. Shows the scene in desktop + mobile artboards via a design-canvas wrapper. |
| `scene.jsx` | The actual `<Scene>` component — photo, panel, buttons, modal. **This is the thing to port.** |
| `scene.css` | All styling: tokens, photo overlays, type, animations, both variants. |
| `design-canvas.jsx` | Prototype-only scaffolding for side-by-side artboards. Do not ship. |
| `assets/guard.jpeg` | The guard photo. Verify rights before shipping. |

## Open questions for product / backend

1. What endpoint should "Wake up the admin" hit? (Slack webhook? Internal API?) Should it rate-limit so a single 404'd visitor can't spam the admin?
2. Should the "Sent!" modal include the request ID / page URL that 404'd, so the admin gets useful debugging context automatically?
3. Confirm the photo rights / replace with original imagery.
4. Should this page also render on 500 / 503, or only on true 404s? (Copy currently says "If you're seeing this page, something went wrong" which works for both.)
