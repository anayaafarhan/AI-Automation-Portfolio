"""Asset ingestion + analysis.

Everything here is classical, weight-free computer vision (Pillow/numpy/scipy
math on pixels) — no pretrained model downloads, so it works identically
offline, in a network-restricted sandbox, or on a laptop. It's honest about
its limits: room-type labels lean on filename hints because reliable
zero-shot scene classification needs a pretrained model, and this pipeline
deliberately doesn't depend on one (see README for why).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}

# keyword -> (category label, narrative order index)
ROOM_KEYWORDS: list[tuple[list[str], str]] = [
    (["exterior", "outside", "front", "facade", "curb", "house", "villa", "entrance"], "Exterior"),
    (["living", "lounge", "sofa", "family"], "Living Room"),
    (["kitchen"], "Kitchen"),
    (["dining"], "Dining Area"),
    (["bed", "bedroom", "master", "suite"], "Bedroom"),
    (["bath", "bathroom", "shower", "tub"], "Bathroom"),
    (["pool", "spa", "jacuzzi"], "Pool"),
    (["view", "balcony", "terrace", "patio", "deck", "rooftop"], "View"),
    (["garden", "yard", "backyard"], "Garden"),
    (["night", "evening", "sunset", "dusk", "golden"], "Golden Hour"),
]
NARRATIVE_ORDER = [
    "Exterior", "Living Room", "Kitchen", "Dining Area", "Bedroom",
    "Bathroom", "Pool", "Garden", "View", "Golden Hour", "Featured Space",
]


@dataclass
class Asset:
    path: Path
    kind: str                      # "image" | "video"
    category: str = "Featured Space"
    quality: float = 0.0
    outdoor_conf: float = 0.0      # 0..1 confidence this frame is outdoor/sky-bearing
    width: int = 0
    height: int = 0
    duration: float = 0.0          # only meaningful for video


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_assets(input_dir: Path) -> list[Asset]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")
    assets = []
    for p in sorted(input_dir.iterdir()):
        ext = p.suffix.lower()
        if ext in IMAGE_EXTS:
            assets.append(Asset(path=p, kind="image"))
        elif ext in VIDEO_EXTS:
            assets.append(Asset(path=p, kind="video"))
    return assets


def label_for_filename(name: str) -> str:
    lname = name.lower()
    for keywords, label in ROOM_KEYWORDS:
        if any(k in lname for k in keywords):
            return label
    return "Featured Space"


# ---------------------------------------------------------------------------
# Classical quality scoring (no pretrained weights)
# ---------------------------------------------------------------------------

def _sharpness(gray: np.ndarray) -> float:
    gy, gx = np.gradient(gray.astype(np.float32))
    gyy, _ = np.gradient(gy)
    _, gxx = np.gradient(gx)
    return float((gyy + gxx).var())


def _exposure_penalty(gray: np.ndarray) -> float:
    mean = gray.mean()
    return abs(mean - 128.0) / 128.0


def _horizon_level_bonus(gray: np.ndarray) -> float:
    """Rewards a level horizon: compares gradient-energy symmetry between
    the top and bottom half's row-wise brightness trend. Crude but free."""
    h = gray.shape[0]
    top_slope = np.polyfit(np.arange(h // 2), gray[: h // 2].mean(axis=1), 1)[0]
    bottom_slope = np.polyfit(np.arange(h // 2), gray[h // 2:].mean(axis=1), 1)[0]
    tilt = abs(top_slope) + abs(bottom_slope)
    return max(0.0, 1.0 - tilt / 5.0) * 0.15


def outdoor_confidence(rgb: np.ndarray) -> float:
    """Heuristic: is there a confident sky region touching the top edge?
    Used to (a) bias category toward Exterior/View/Pool and (b) gate the
    sky-parallax motion effect. Pure color/texture thresholding, no ML."""
    h, w, _ = rgb.shape
    top = rgb[: max(1, h // 2)]
    r, g, b = top[..., 0].astype(np.float32), top[..., 1].astype(np.float32), top[..., 2].astype(np.float32)
    brightness = (r + g + b) / 3
    blueish = (b - r) > 8
    bright_enough = brightness > 120
    sky_like = blueish & bright_enough
    if sky_like.mean() < 0.05:
        return 0.0
    labeled, n = ndimage.label(sky_like)
    if n == 0:
        return 0.0
    top_row_labels = set(labeled[0][labeled[0] > 0].tolist())
    if not top_row_labels:
        return 0.0
    sizes = ndimage.sum(sky_like, labeled, index=list(top_row_labels))
    best_frac = max(sizes) / sky_like.size
    return float(np.clip(best_frac * 2.2, 0.0, 1.0))


def score_asset(path: Path, small: Image.Image) -> tuple[float, float]:
    gray = np.array(small.convert("L"))
    rgb = np.array(small.convert("RGB"))
    sharp = _sharpness(gray)
    quality = np.log1p(sharp) - 2.2 * _exposure_penalty(gray) + _horizon_level_bonus(gray)
    outdoor = outdoor_confidence(rgb)
    return float(quality), outdoor


# ---------------------------------------------------------------------------
# Video probing
# ---------------------------------------------------------------------------

def probe_video(path: Path) -> tuple[float, int, int]:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "json", str(path),
    ]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    data = json.loads(out.stdout.decode())
    stream = data["streams"][0]
    duration = float(stream.get("duration", 0.0) or 0.0)
    if duration <= 0:
        # some containers omit stream duration; fall back to format duration
        cmd2 = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]
        out2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        duration = float(json.loads(out2.stdout.decode())["format"].get("duration", 4.0))
    return duration, int(stream["width"]), int(stream["height"])


def middle_frame(path: Path, at_seconds: float, out_png: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(at_seconds), "-i", str(path), "-frames:v", "1", str(out_png)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def analyze_assets(input_dir: Path, work_dir: Path) -> list[Asset]:
    assets = discover_assets(input_dir)
    if not assets:
        raise SystemExit(
            f"No photos or videos found in {input_dir}/ "
            f"(looked for {sorted(IMAGE_EXTS | VIDEO_EXTS)})"
        )

    kept: list[Asset] = []
    for a in assets:
        try:
            if a.kind == "image":
                with Image.open(a.path) as im:
                    im = im.convert("RGB")
                    a.width, a.height = im.size
                    small = im.resize((320, int(320 * im.height / im.width)))
                q, outdoor = score_asset(a.path, small)
            else:
                a.duration, a.width, a.height = probe_video(a.path)
                mid = work_dir / f"probe_{a.path.stem}.png"
                middle_frame(a.path, min(a.duration / 2, max(a.duration - 0.2, 0.1)), mid)
                with Image.open(mid) as im:
                    small = im.convert("RGB").resize((320, int(320 * im.height / im.width)))
                q, outdoor = score_asset(a.path, small)
                q += 0.6  # real motion beats synthetic Ken Burns of the same scene
        except Exception as e:
            print(f"  ! skipping unreadable asset {a.path.name}: {e}")
            continue

        a.quality = q
        a.outdoor_conf = outdoor
        label = label_for_filename(a.path.stem)
        if label == "Featured Space" and outdoor > 0.5:
            label = "View"
        a.category = label
        kept.append(a)

    if not kept:
        raise SystemExit("No readable/usable assets survived analysis.")
    return kept
