# Cinematic Airbnb / Luxury Property Video Generator (100% Free & Local)

One folder of property photos/videos in, one polished vertical (9:16)
20–30s cinematic property reel out. One command:

```bash
python3 make_reel.py
```

No paid APIs, no subscriptions beyond what you already have, no accounts,
no uploads. Everything runs on your own machine with `ffmpeg` and Python.

---

## Research: what's genuinely possible at $0 (read this first)

Before writing any code, this was tested directly rather than guessed. Two
hard facts about the build environment mattered: it has **no GPU**, and its
network policy **blocks huggingface.co** outright (confirmed via a 403 at
the proxy level). That rules out more than it might seem, so here's the
honest landscape:

| Option | Cost | Genuinely $0? | API? | Local? | GPU needed | Quality | Realistic 4–6s clip? | Automatable? |
|---|---|---|---|---|---|---|---|---|
| Runway Gen-3/4, Pika 1.5 | Paid / credit trial | ❌ trial credits run out | Paid API only | No | N/A | High | Yes | No — paywall |
| Kling, Haiper, PixVerse, Luma Dream Machine | Free web credits | ⚠️ capped, browser-only | No free API | No | N/A | High, but alters objects/geometry | Yes | **No** — no scriptable free API, login/CAPTCHA-gated, ToS forbids bulk scripting |
| Stable Video Diffusion, AnimateDiff, CogVideoX-I2V, LTX-Video, Wan2.1 (open-weight, local) | $0 license | ✅ cost-wise, but weights ship from huggingface.co, **blocked here** | No | Yes, with a GPU | 8–24GB VRAM (this box has **0**) | Medium — documented to warp geometry, invent/remove objects, flicker | Technically yes on a real GPU | Only on a machine with both a capable GPU *and* HF access |
| HF Spaces via scripted API | Free | ⚠️ fragile | Unofficial | No | N/A | Variable | Sometimes | No — blocked here, and queue/ToS make it unreliable generally |
| LeiaPix / Immersity AI (depth-based 2.5D) | Free tier | ⚠️ usable, capped | No public API | No | N/A | Good "living photo" parallax | ~Yes, one shot | No — browser-only, manual upload |
| **Classical CV: virtual-camera Ken Burns + selective sky-layer parallax + color grade** | $0 | ✅ works right now | No | Yes | None, CPU only | Cinematic when done with restraint; zero hallucination risk | Motion reads as intentional camera work | ✅ Yes, entirely |
| **Your own real video footage** (walkthrough/drone) | $0 | ✅ | No | Yes | None | Best possible — it's real | N/A, already real | ✅ Yes — trimmed/cropped/graded automatically |

**The honest conclusion:** every route that *generates new video content*
from a still photo (diffusion image-to-video) either costs money, caps out
on a browser-only free tier that can't be scripted, or — even where the
license is free — is well documented to distort exactly the things a
real-estate client cares about (wall count, window placement, furniture,
room geometry). That's not a workaround-able gap; it's the current state
of the technology. Claiming one of those as "the $0 solution" here would
be dishonest about either automation or accuracy — so this tool doesn't.

### What this tool does instead

A **deterministic "virtual camera" engine**: real per-shot camera moves
(push-in, pull-back, slow pan/dolly, restrained hold) chosen by analyzing
each photo's composition, plus a **selective two-layer parallax effect for
sky/exterior shots** — the sky pans independently from the building at a
damped rate (real, physically-motivated parallax), composited on top of an
**unaltered** foreground layer. This is safe by construction: every camera
move is a pure affine crop/zoom/pan of your original pixels, so nothing can
be invented or warped. The one place synthetic motion touches anything
beyond simple reframing is empty sky — the one region of a real-estate
photo where it's actually safe to move pixels independently, because
there's no architecture there to distort.

Real video clips in your `input/` folder are used directly (trimmed,
cropped, color-matched) — real motion always beats synthetic motion, with
zero distortion risk, and always outranks a synthetic Ken-Burns pass of the
same subject.

If open-weight image-to-video models become runnable in your situation
later (your own GPU machine, unrestricted network), the storyboard this
tool produces (`storyboard.json`, with per-shot focal points and motion
intent already worked out) is a reasonable hand-off point for that — but
this pipeline itself deliberately does not depend on one.

---

## Requirements

- **ffmpeg** (free, open-source): `sudo apt install ffmpeg` / `brew install ffmpeg` / ffmpeg.org for Windows
- **Python 3.10+**
- `pip3 install -r requirements.txt` (Pillow, numpy, scipy — all free, all local, no model weights downloaded)

## Usage

```bash
# 1. Drop property photos and/or short video clips into input/
#    Filenames with room keywords ("kitchen", "pool", "bedroom", "view",
#    "exterior"...) improve auto-classification; generic names still work,
#    just fall back to quality-based ordering.

# 2. (optional) Drop one royalty-free mp3/wav into music/

# 3. (optional) Copy config.example.json -> config.json and fill in your
#    property name, location, amenities, and CTA.

# 4. Generate
python3 make_reel.py --config config.json

# or pass everything on the command line:
python3 make_reel.py --property-name "Sunset Villa" --location "Malibu, California" \
  --amenities "PRIVATE POOL,OCEAN VIEW,5 BEDROOMS" --cta "BOOK YOUR STAY"
```

Outputs:
- `output/final_reel.mp4` — full-quality vertical 1080x1920 master
- `output/preview.mp4` — smaller/faster encode for quick review or sharing
- `output/storyboard.json` — the full editable plan (shot order, category,
  camera move, focal point, sky-parallax flag, duration, captions)

Re-render after hand-editing the storyboard without repeating analysis:

```bash
python3 make_reel.py --storyboard output/storyboard.json
```

### Demo mode (for showing prospective clients)

```bash
python3 make_reel.py --demo
```

Generates a synthetic sample property photo set (clearly-synthetic
gradient/shape stand-ins, not real photos) into `input/` and runs the full
pipeline end to end — including the sky-parallax path — so you can see the
finished pacing, grade, typography, and motion before pointing it at real
listing photos. Note: because the demo images are flat synthetic gradients,
you may see faint horizontal "banding" from video compression that would
not appear on a real photo (real photos have enough natural texture/noise
to hide it) — that's a property of the demo content, not the pipeline.

### Options

```
--input             Folder of photos/videos (default: input/)
--music             Folder to check for a royalty-free track (default: music/)
--output            Output folder (default: output/)
--config            Path to a config.json
--property-name     Overlay on the opening title card
--location           "                      "
--amenities         Comma-separated callouts, e.g. "PRIVATE POOL,OCEAN VIEW,5 BEDROOMS"
--cta               Closing card text (default: "BOOK YOUR STAY")
--max-shots         Cap on number of shots used (default: 8)
--storyboard        Reuse/edit an existing storyboard.json instead of re-selecting
--font-serif/--font-sans   Override title/body fonts
--no-sky-parallax   Disable the sky-layer parallax effect
--no-grain          Disable the subtle film-grain pass
--demo              Generate synthetic sample assets first
--keep-work-dir     Keep intermediate per-shot clips for debugging
```

---

## How it works

1. **Analysis** (`pipeline/analysis.py`) — every photo/video is scored on
   sharpness, exposure, and horizon level (classical gradient/statistics
   math, no pretrained model), and checked for a confident outdoor/sky
   region. Room type comes from filename keywords, with an outdoor-signal
   fallback for generically-named exterior/view shots. This is intentionally
   honest about its limits: true zero-shot scene classification needs a
   pretrained vision model, and this pipeline deliberately doesn't carry
   that dependency (see the research table above for why).

2. **Storyboard** (`pipeline/storyboard.py`) — the best shot per room
   category is kept first (so you don't get two kitchens eating the
   runway), ordered into a tour (exterior → living → kitchen → bedroom →
   bathroom → pool → view), each photo gets a focal point (gradient-energy
   centroid, biased away from the frame edges) and a camera move chosen
   from its composition — a highly symmetric exterior gets a minimal
   respectful hold, an off-center room gets a push toward its focal point,
   a wide outdoor shot gets a slow pan. Shot duration is solved
   automatically so the assembled runtime lands near 25s regardless of how
   many shots were selected. Amenity callouts are spread sparsely (never
   one per shot) across the middle of the cut. Written to
   `storyboard.json` so every decision is inspectable and editable.

3. **Motion** (`pipeline/motion.py`) — still photos become clips via
   ffmpeg's `zoompan` filter: a pure crop/zoom/pan of the original pixels,
   which is why it can't invent or warp geometry. For shots with a
   confidently-detected sky (classical color/connected-component
   thresholding, feathered mask edge, confidence-gated so it silently
   falls back to plain camera motion when uncertain), a second sky-only
   layer is composited on top with a damped version of the same move —
   real parallax, applied only to empty sky. Real video clips are trimmed
   and cropped, never touched by the synthetic motion engine.

4. **Assembly & grade** (`pipeline/grade_assemble.py`) — clips are joined
   with a single restrained crossfade style (no wipes/spins), then given a
   consistent cinematic grade: gentle S-curve contrast, light teal/orange
   separation, a soft vignette, and optional fine film grain.

5. **Sound** (`pipeline/audio.py`) — a locally-synthesized ambient pad
   (layered tones + soft pink noise, low-passed, with a slow swell into
   the closing CTA) by default. If you drop a royalty-free track into
   `music/`, that's used instead — trimmed/looped with fades. See "Why
   music is synthesized" below.

6. **Typography** (`pipeline/typography.py`) — an opening title card
   (property name + location), a small number of amenity callouts, and a
   closing CTA card. Deliberately sparse — not a caption on every shot.

### Why music is synthesized instead of downloaded

There's no way to automatically fetch *licensed* music for $0 without
either an API/subscription (Epidemic Sound, Artlist, etc. all cost money)
or scraping a streaming service (legally unsound). So the default is a
simple ffmpeg-synthesized ambient bed — zero cost, zero licensing risk. For
a real score, it's a one-time manual step: grab a track from a free,
no-attribution-required library (YouTube Audio Library, Pixabay Music,
Chosic) and drop it in `music/`. That one step can't be automated safely
without either a paid licensing API or legally uncertain scraping, so it's
intentionally left to you.

## Notes & honest limits

- Room-type labels lean on filename keywords; name your files
  descriptively for best results, or hand-edit `storyboard.json`.
- Sky parallax only activates when a sky region is confidently detected
  (connected, touches the top edge, 5–55% of frame) — it silently and
  safely falls back to plain camera motion otherwise. It will not activate
  on interior shots with small windows, by design.
- The synthesized ambient track is a placeholder bed, not a polished
  score — swap in your own royalty-free track for anything client-facing.
- Rendering ~8 vertical clips with camera moves, grading, and captions
  typically takes well under two minutes on a modern CPU; no GPU required.
