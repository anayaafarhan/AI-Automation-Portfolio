#!/usr/bin/env python3
"""
Airbnb Cinematic Reel Generator
--------------------------------
Turns a folder of property photos into a 20-30s vertical (9:16) cinematic
real-estate reel: automatic photo selection, storyboard, Ken Burns motion,
crossfade transitions, on-screen captions, ambient background music, and a
final MP4 render.

100% free / local / offline. No paid APIs, no cloud services, no API keys.
Stack: Python + Pillow + numpy (selection/scoring) and ffmpeg (everything
video/audio: motion, transitions, captions, music synthesis, encoding).

Usage:
    python3 reel_generator.py --input input_photos --output output/reel.mp4 \
        --property-name "Sunset Villa" --tagline "Your private escape"

Run --help for all options.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageFilter
except ImportError:
    sys.exit(
        "Missing dependencies. Install with:\n"
        "    pip3 install -r requirements.txt"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 1080, 1920          # 9:16 vertical
FPS = 30
CLIP_DURATION = 3.2                 # seconds of screen time per photo
XFADE_DURATION = 0.6                # crossfade overlap between clips
MAX_CLIPS = 8
MIN_CLIPS = 5
TARGET_TOTAL = (20, 30)             # seconds, informational target range

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # macOS
    "C:/Windows/Fonts/arialbd.ttf",                         # Windows
]

# Room keywords -> polished caption label. Matched against the filename.
ROOM_KEYWORDS = [
    (["exterior", "outside", "front", "facade", "house", "villa"], "Welcome Home"),
    (["living", "lounge", "sofa"], "Living Room"),
    (["kitchen"], "Chef's Kitchen"),
    (["dining"], "Dining Area"),
    (["bed", "bedroom", "master"], "Bedroom"),
    (["bath", "bathroom"], "Bathroom"),
    (["pool", "spa", "jacuzzi"], "Private Pool"),
    (["view", "balcony", "terrace", "patio", "deck"], "The View"),
    (["garden", "yard"], "Garden"),
    (["night", "evening", "sunset"], "Golden Hour"),
]

# Preferred narrative order (index into ROOM_KEYWORDS groups), exterior first,
# view/night as a closer.
NARRATIVE_ORDER = [
    "Welcome Home", "Living Room", "Kitchen".replace("Kitchen", "Chef's Kitchen"),
    "Dining Area", "Bedroom", "Bathroom", "Private Pool", "Garden",
    "The View", "Golden Hour",
]

# Ken Burns motion presets, cycled across clips for variety.
MOTION_PRESETS = ["zoom_in_center", "pan_left_right", "zoom_out_center", "pan_right_left"]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Shot:
    path: Path
    caption: str
    duration: float = CLIP_DURATION
    motion: str = "zoom_in_center"
    score: float = 0.0


# ---------------------------------------------------------------------------
# Step 1: Image scoring & selection (Pillow + numpy, no paid vision API)
# ---------------------------------------------------------------------------

def sharpness_score(img_gray: "np.ndarray") -> float:
    """Variance of a Laplacian-like second-derivative filter. Higher = sharper."""
    gy, gx = np.gradient(img_gray.astype(np.float32))
    gyy, _ = np.gradient(gy)
    _, gxx = np.gradient(gx)
    laplacian = gyy + gxx
    return float(laplacian.var())


def brightness_penalty(img_gray: "np.ndarray") -> float:
    """0 = ideal brightness, higher = too dark or too blown out."""
    mean = img_gray.mean()
    ideal = 128.0
    return abs(mean - ideal) / ideal


def score_image(path: Path) -> float:
    with Image.open(path) as im:
        im = im.convert("L").resize((320, 320))
        arr = np.array(im)
    sharp = sharpness_score(arr)
    bright_pen = brightness_penalty(arr)
    # Normalize sharpness (empirically photos land in the low hundreds to
    # low thousands for this metric); combine into one comparable score.
    return math.log1p(sharp) - 2.0 * bright_pen


def label_for_filename(name: str) -> str:
    lname = name.lower()
    for keywords, label in ROOM_KEYWORDS:
        if any(k in lname for k in keywords):
            return label
    return "Featured Space"


def select_and_order_shots(input_dir: Path, max_clips: int) -> list[Shot]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
    files = [p for p in sorted(input_dir.iterdir()) if p.suffix.lower() in exts]
    if not files:
        sys.exit(f"No photos found in {input_dir} (looked for {sorted(exts)}).")

    shots = []
    for p in files:
        try:
            score = score_image(p)
        except Exception as e:
            print(f"  ! skipping unreadable image {p.name}: {e}")
            continue
        shots.append(Shot(path=p, caption=label_for_filename(p.stem), score=score))

    if not shots:
        sys.exit("No readable photos survived scoring.")

    # Drop the worst quartile if we have plenty of photos to choose from.
    shots.sort(key=lambda s: s.score, reverse=True)
    keep_count = max(min(len(shots), max_clips), min(MIN_CLIPS, len(shots)))
    shots = shots[:keep_count]

    # Reorder into a narrative: exterior -> living spaces -> bed/bath ->
    # amenities -> view/closer. Photos whose label isn't in the narrative
    # list fall back to score order, inserted after the opener.
    def narrative_key(s: Shot):
        try:
            idx = NARRATIVE_ORDER.index(s.caption)
        except ValueError:
            idx = len(NARRATIVE_ORDER) - 1  # treat unknowns as mid-tour
        return idx

    shots.sort(key=narrative_key)

    for i, s in enumerate(shots):
        s.motion = MOTION_PRESETS[i % len(MOTION_PRESETS)]

    return shots


# ---------------------------------------------------------------------------
# Step 2: Storyboard (human-editable JSON — re-run to skip re-selection)
# ---------------------------------------------------------------------------

def write_storyboard(shots: list[Shot], path: Path, property_name: str, tagline: str) -> None:
    data = {
        "property_name": property_name,
        "tagline": tagline,
        "shots": [
            {
                "path": str(s.path),
                "caption": s.caption,
                "duration": s.duration,
                "motion": s.motion,
            }
            for s in shots
        ],
    }
    path.write_text(json.dumps(data, indent=2))


def load_storyboard(path: Path) -> tuple[list[Shot], str, str]:
    data = json.loads(path.read_text())
    shots = [
        Shot(
            path=Path(sh["path"]),
            caption=sh["caption"],
            duration=float(sh.get("duration", CLIP_DURATION)),
            motion=sh.get("motion", "zoom_in_center"),
        )
        for sh in data["shots"]
    ]
    return shots, data.get("property_name", ""), data.get("tagline", "")


# ---------------------------------------------------------------------------
# Step 3: ffmpeg helpers
# ---------------------------------------------------------------------------

def find_font() -> str:
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    sys.exit("No usable font found. Pass --font /path/to/font.ttf")


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        print(result.stdout.decode(errors="replace"))
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")


def zoompan_expr(motion: str, duration: float, fps: int) -> tuple[str, str, str]:
    """Returns (zoom_expr, x_expr, y_expr) for the ffmpeg zoompan filter."""
    frames = int(duration * fps)
    if motion == "zoom_in_center":
        z = f"min(zoom+{0.0022:.5f},1.18)"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "zoom_out_center":
        z = f"if(eq(on,0),1.18,max(zoom-{0.0022:.5f},1.0))"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "pan_left_right":
        z = "1.12"
        x = f"(iw-iw/zoom)*(on/{max(frames-1,1)})"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "pan_right_left":
        z = "1.12"
        x = f"(iw-iw/zoom)*(1-on/{max(frames-1,1)})"
        y = "ih/2-(ih/zoom/2)"
    else:
        z, x, y = "1.1", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return z, x, y


def build_clip(shot: Shot, index: int, work_dir: Path, font: str, property_name: str) -> Path:
    """Render one still photo into a Ken-Burns video clip with a caption."""
    out_path = work_dir / f"clip_{index:02d}.mp4"
    z, x, y = zoompan_expr(shot.motion, shot.duration, FPS)
    frames = int(shot.duration * FPS)

    caption = shot.caption.replace("'", "\u2019").replace(":", "\\:")
    fade = 0.4
    dur = shot.duration
    alpha_expr = f"if(lt(t\\,{fade})\\,t/{fade}\\,if(gt(t\\,{dur-fade})\\,({dur}-t)/{fade}\\,1))"

    draw_caption = (
        f"drawtext=fontfile='{font}':text='{caption}':"
        f"fontcolor=white:fontsize=64:x=(w-text_w)/2:y=h-320:"
        f"box=1:boxcolor=black@0.35:boxborderw=24:alpha='{alpha_expr}'"
    )
    draw_brand = (
        f"drawtext=fontfile='{font}':text='{property_name}':"
        f"fontcolor=white:fontsize=40:x=(w-text_w)/2:y=140:"
        f"box=1:boxcolor=black@0.25:boxborderw=18:alpha='{alpha_expr}'"
    ) if property_name else None

    vf_parts = [
        f"scale={WIDTH*2}:{HEIGHT*2}:force_original_aspect_ratio=increase",
        f"crop={WIDTH*2}:{HEIGHT*2}",
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}",
        draw_caption,
    ]
    if draw_brand:
        vf_parts.append(draw_brand)
    vf = ",".join(vf_parts)

    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(shot.path),
        "-t", str(shot.duration),
        "-vf", vf,
        "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
        str(out_path),
    ])
    return out_path


def concat_with_xfade(clips: list[Path], durations: list[float], work_dir: Path) -> Path:
    """Chain clips with crossfade transitions into one silent video."""
    out_path = work_dir / "video_concat.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], out_path)
        return out_path

    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]

    filter_parts = []
    cumulative = durations[0]
    prev_label = "0"
    for i in range(1, len(clips)):
        offset = cumulative - XFADE_DURATION
        cur_label = f"v{i}"
        transition = "fade" if i % 2 == 0 else "smoothleft"
        filter_parts.append(
            f"[{prev_label}][{i}]xfade=transition={transition}:"
            f"duration={XFADE_DURATION}:offset={offset:.3f}[{cur_label}]"
        )
        prev_label = cur_label
        cumulative = cumulative + durations[i] - XFADE_DURATION

    filter_complex = ";".join(filter_parts)
    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
        str(out_path),
    ])
    return out_path


def total_duration_with_xfade(durations: list[float]) -> float:
    if not durations:
        return 0.0
    total = durations[0]
    for d in durations[1:]:
        total += d - XFADE_DURATION
    return total


# ---------------------------------------------------------------------------
# Step 4: Music — either a user-supplied royalty-free track, or a locally
# synthesized ambient pad (no download, no licensing risk, zero cost).
# ---------------------------------------------------------------------------

def find_user_music(music_dir: Path) -> Path | None:
    if not music_dir.exists():
        return None
    exts = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
    for p in sorted(music_dir.iterdir()):
        if p.suffix.lower() in exts:
            return p
    return None


def synthesize_ambient_music(duration: float, out_path: Path) -> None:
    """Layer a few sine tones + soft noise into a slow ambient pad using
    ffmpeg's built-in audio synthesis (lavfi). No samples, no downloads."""
    d = duration + 1.0
    filt = (
        f"sine=frequency=110:duration={d}[a];"
        f"sine=frequency=164.81:duration={d}[b];"
        f"sine=frequency=220:duration={d}[c];"
        f"anoisesrc=color=pink:amplitude=0.02:duration={d}[n];"
        f"[a][b][c][n]amix=inputs=4:weights='1 0.8 0.6 0.5':normalize=0,"
        f"tremolo=f=0.15:d=0.3,"
        f"lowpass=f=1200,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={max(d-2,0)}:d=2,"
        f"volume=0.35"
    )
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", filt,
        "-t", str(duration),
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ])


def prepare_audio(music_dir: Path, duration: float, work_dir: Path) -> Path:
    user_track = find_user_music(music_dir)
    out_path = work_dir / "audio.m4a"
    if user_track:
        print(f"  using your music track: {user_track.name}")
        run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(user_track),
            "-t", str(duration),
            "-af", f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(duration-1.5,0)}:d=1.5,volume=0.7",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ])
    else:
        print("  no track in music/, synthesizing a free ambient pad locally")
        synthesize_ambient_music(duration, out_path)
    return out_path


# ---------------------------------------------------------------------------
# Step 5: Final mux
# ---------------------------------------------------------------------------

def mux_final(video: Path, audio: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ])


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a cinematic Airbnb reel from a photo folder.")
    ap.add_argument("--input", default="input_photos", help="Folder of property photos")
    ap.add_argument("--music", default="music", help="Optional folder with a royalty-free track (mp3/wav)")
    ap.add_argument("--output", default="output/reel.mp4", help="Output MP4 path")
    ap.add_argument("--property-name", default="", help="Overlay text, e.g. 'Sunset Villa'")
    ap.add_argument("--tagline", default="", help="Reserved for future title-card use")
    ap.add_argument("--max-clips", type=int, default=MAX_CLIPS)
    ap.add_argument("--storyboard", default=None, help="Path to a storyboard.json to reuse/edit instead of re-selecting photos")
    ap.add_argument("--font", default=None, help="Path to a .ttf font for captions")
    ap.add_argument("--keep-work-dir", action="store_true", help="Keep intermediate clips for debugging")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH. Install it (it's free): https://ffmpeg.org/download.html")

    input_dir = Path(args.input)
    music_dir = Path(args.music)
    out_path = Path(args.output)
    font = args.font or find_font()

    storyboard_path = Path(args.storyboard) if args.storyboard else out_path.parent / "storyboard.json"

    if args.storyboard and Path(args.storyboard).exists():
        print(f"[1/5] Loading existing storyboard: {args.storyboard}")
        shots, sb_name, sb_tagline = load_storyboard(Path(args.storyboard))
        property_name = args.property_name or sb_name
    else:
        print(f"[1/5] Scanning & scoring photos in {input_dir} ...")
        shots = select_and_order_shots(input_dir, args.max_clips)
        property_name = args.property_name
        for s in shots:
            print(f"       + {s.path.name:30s} -> '{s.caption}' (score {s.score:.2f}, motion {s.motion})")
        storyboard_path.parent.mkdir(parents=True, exist_ok=True)
        write_storyboard(shots, storyboard_path, property_name, args.tagline)
        print(f"       storyboard written to {storyboard_path} (edit & re-run with --storyboard to customize)")

    total_est = total_duration_with_xfade([s.duration for s in shots])
    print(f"       {len(shots)} shots selected, estimated runtime ~{total_est:.1f}s "
          f"(target {TARGET_TOTAL[0]}-{TARGET_TOTAL[1]}s)")

    work_dir = Path(tempfile.mkdtemp(prefix="airbnb_reel_"))
    try:
        print("[2/5] Rendering Ken Burns clips + captions ...")
        clip_paths = []
        for i, shot in enumerate(shots):
            clip_paths.append(build_clip(shot, i, work_dir, font, property_name))
            print(f"       clip {i+1}/{len(shots)} done")

        print("[3/5] Chaining crossfade transitions ...")
        video_only = concat_with_xfade(clip_paths, [s.duration for s in shots], work_dir)

        print("[4/5] Preparing background music ...")
        audio_path = prepare_audio(music_dir, total_est, work_dir)

        print("[5/5] Muxing final MP4 ...")
        mux_final(video_only, audio_path, out_path)

        print(f"\nDone: {out_path.resolve()}")
    finally:
        if args.keep_work_dir:
            print(f"(intermediate files kept at {work_dir})")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
