# Airbnb Cinematic Video Generator (100% Free & Local)

Turns a folder of property photos into a **20–30s vertical (9:16) cinematic
real-estate reel** — automatic photo selection, storyboard, Ken Burns
motion, crossfade transitions, on-screen captions, background music, and a
final MP4. No paid APIs, no subscriptions, no cloud rendering. Everything
runs on your own machine.

## What's automated, and with what free tool

| Stage | Tool | Cost |
|---|---|---|
| Photo quality scoring (sharpness/exposure) & selection | Python + Pillow + numpy | Free, local |
| Storyboard (order, captions, motion per shot) | Plain Python, output as editable `storyboard.json` | Free |
| Ken Burns cinematic zoom/pan | `ffmpeg` `zoompan` filter | Free, open-source |
| Crossfade transitions between shots | `ffmpeg` `xfade` filter | Free, open-source |
| Burned-in captions ("Living Room", property name, fade in/out) | `ffmpeg` `drawtext` + system fonts (DejaVu/Liberation) | Free |
| Background music | `ffmpeg` audio synthesis (`sine`/`anoisesrc`/`tremolo`/`lowpass`) generates a soft ambient pad locally — **or** drop your own royalty-free track into `music/` | Free |
| Final vertical MP4 render (1080x1920, H.264/AAC) | `ffmpeg` | Free, open-source |

Nothing here calls an external API, uploads your photos anywhere, or
requires an account. The only two dependencies are `ffmpeg` (a CLI tool)
and two small Python libraries (`Pillow`, `numpy`) — all free and
open-source.

### Why music is synthesized instead of downloaded
There's no way to automatically fetch *licensed* music for $0 without an
API/subscription (Epidemic Sound, Artlist, etc. all cost money, and
scraping YouTube/streaming services isn't legal). So this tool defaults to
generating a simple ambient pad with `ffmpeg`'s built-in audio synthesis —
zero cost, zero licensing risk, good enough as a placeholder bed.

If you want a real music track, it's a one-time manual step: grab a track
from a free, no-attribution-required library — e.g. **YouTube Audio
Library**, **Pixabay Music**, or **Chosic** — and drop the MP3/WAV into the
`music/` folder. The script auto-detects it, loops/trims it to length, and
fades it in/out. This one step can't be automated safely without either a
paid licensing API or legally uncertain scraping, so it's intentionally
left to you.

## Requirements

- **ffmpeg** (free, open-source): `sudo apt install ffmpeg` (Linux),
  `brew install ffmpeg` (Mac), or download from ffmpeg.org (Windows).
- **Python 3.9+**
- `pip3 install -r requirements.txt`

## Usage

```bash
# 1. Drop your property photos into input_photos/
#    (any filenames; naming them with room keywords like "kitchen",
#    "living_room", "pool", "bedroom", "view" improves auto-captions)

# 2. (optional) Drop one royalty-free mp3/wav into music/

# 3. Generate the reel
python3 reel_generator.py \
  --input input_photos \
  --output output/reel.mp4 \
  --property-name "Sunset Villa"
```

The script prints its picks and writes `output/storyboard.json` — an
editable plan (photo order, captions, motion, per-shot duration). Tweak it
by hand, then re-render without re-running photo selection:

```bash
python3 reel_generator.py --storyboard output/storyboard.json --output output/reel.mp4
```

### Options

```
--input           Folder of property photos (default: input_photos)
--music           Folder to check for a royalty-free track (default: music)
--output          Output MP4 path (default: output/reel.mp4)
--property-name   Text overlay at the top, e.g. "Sunset Villa"
--max-clips       Max number of photos to use (default: 8)
--storyboard      Reuse/edit an existing storyboard.json instead of re-selecting
--font            Path to a .ttf font for captions (auto-detected by default)
--keep-work-dir   Keep intermediate per-shot clips for debugging
```

## How it works

1. **Selection** — every photo is scored for sharpness (Laplacian-variance
   approximation) and exposure (distance from mid-gray). The lowest-quality
   quartile is dropped when there are more photos than needed, and the
   rest are ordered into a "tour": exterior → living areas → kitchen →
   bedroom → bathroom → pool/amenities → view, using keywords found in each
   filename (falls back to quality-score order for anything unrecognized).
2. **Storyboard** — the selection above is written to `storyboard.json` so
   it's inspectable and editable before rendering.
3. **Motion** — each still image is rendered into its own short clip with
   one of four alternating Ken Burns moves (zoom in, zoom out, pan
   left→right, pan right→left) via `ffmpeg zoompan`, cropped to 1080x1920.
4. **Captions** — room labels and the property name are burned in with
   `ffmpeg drawtext`, fading in/out per clip.
5. **Transitions** — clips are chained with `ffmpeg xfade` crossfades.
6. **Music** — your track (if provided) or a synthesized ambient pad is
   trimmed/looped to the video length with fade in/out.
7. **Render** — video and audio are muxed into the final vertical MP4.

## Notes & limits (honest version)

- This is intentionally the **simplest working version** — one Python
  script, no web UI, no database, no queue. Easy to read and extend.
- Caption text comes from filename keywords, not real computer vision. For
  best results, name your files descriptively (`03_kitchen.jpg`,
  `05_pool_view.jpg`, etc.) or hand-edit `storyboard.json`.
- The synthesized ambient track is a simple placeholder bed, not a
  polished score — swap in your own royalty-free track for anything
  client-facing.
- Rendering ~8 vertical clips with Ken Burns + captions typically takes
  well under a minute on a modern CPU; no GPU required.
