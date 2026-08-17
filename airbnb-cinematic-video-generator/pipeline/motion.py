"""Cinematic motion engine.

Two kinds of shots:
  - real video clips: trimmed and cropped, used as-is (real motion always
    beats synthetic motion, and carries zero distortion risk).
  - still photos: rendered into a "virtual camera" clip using ffmpeg's
    zoompan filter — a pure affine crop/zoom/pan of the ORIGINAL pixels.
    That's the safety property that matters here: no pretrained model is
    inventing or warping content, so architecture can't drift.

For outdoor shots with a confidently-detected sky, a second, independent
"sky layer" is composited on top with a damped version of the same camera
move — real differential parallax (the far layer moves less than the near
layer), applied only to the one region of a real-estate photo where
compositing synthetic motion is actually safe: empty sky.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

from .config import Config, WIDTH, HEIGHT, FPS
from .storyboard import Shot, MOTION_PUSH_IN, MOTION_PULL_BACK, MOTION_SLOW_PAN, MOTION_HOLD_DRIFT
from . import typography

OVERSAMPLE = 2  # headroom multiplier for zoompan's source canvas


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        print(result.stdout.decode(errors="replace"))
        raise RuntimeError(f"ffmpeg command failed: {' '.join(cmd)}")


# ---------------------------------------------------------------------------
# Camera-move expressions (pure affine — cannot warp geometry)
# ---------------------------------------------------------------------------

def _zoom_x_y(motion: str, fx: float, fy: float, max_zoom: float, frames: int, zoom_damp: float = 1.0) -> tuple[str, str, str]:
    """zoom_damp < 1.0 scales down how far this layer's zoom/pan travels —
    used to give the sky layer a slower "distant" rate than the foreground
    for real differential parallax, physically consistent with a near/far
    layer under camera dolly or pan motion."""
    damped_max_zoom = 1.0 + (max_zoom - 1.0) * zoom_damp
    rate = (damped_max_zoom - 1.0) / max(frames, 1)

    if motion == MOTION_PUSH_IN:
        z = f"min(zoom+{rate:.6f},{damped_max_zoom:.4f})"
        x = f"{fx:.3f}*iw-(iw/zoom/2)"
        y = f"{fy:.3f}*ih-(ih/zoom/2)"
    elif motion == MOTION_PULL_BACK:
        z = f"if(eq(on,0),{damped_max_zoom:.4f},max(zoom-{rate:.6f},1.0))"
        x = f"{fx:.3f}*iw-(iw/zoom/2)"
        y = f"{fy:.3f}*ih-(ih/zoom/2)"
    elif motion == MOTION_SLOW_PAN:
        z_const = 1.0 + (min(max_zoom, 1.10) - 1.0) * zoom_damp
        z_const = max(z_const, 1.001)
        z = f"{z_const:.4f}"
        pan_room = 1 - 1 / z_const  # fraction of iw available to pan across
        lo, hi = 0.5 - pan_room * 0.42, 0.5 + pan_room * 0.42
        start, end = (hi, lo) if fx >= 0.5 else (lo, hi)
        n = max(frames - 1, 1)
        x = f"({start:.4f}+({end:.4f}-{start:.4f})*(on/{n}))*iw-(iw/zoom/2)"
        y = f"{fy:.3f}*ih-(ih/zoom/2)"
    else:  # HOLD_DRIFT — minimal movement for symmetric/architectural shots
        z_end = 1.0 + (min(max_zoom, 1.05) - 1.0) * zoom_damp
        rate2 = (z_end - 1.0) / max(frames, 1)
        z = f"min(zoom+{rate2:.6f},{z_end:.4f})"
        x = "0.5*iw-(iw/zoom/2)"
        y = "0.5*ih-(ih/zoom/2)"
    return z, x, y


def _dampen(fx: float, factor: float) -> float:
    return 0.5 + (fx - 0.5) * factor


def _zoompan_chain(zoom: str, x: str, y: str, frames: int) -> str:
    return (
        f"scale={WIDTH*OVERSAMPLE}:{HEIGHT*OVERSAMPLE}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH*OVERSAMPLE}:{HEIGHT*OVERSAMPLE},"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    )


# ---------------------------------------------------------------------------
# Sky layer extraction (classical CV, confidence-gated, feathered edge)
# ---------------------------------------------------------------------------

def make_sky_cutout(image_path: Path, out_png: Path) -> bool:
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        small = im.resize((max(1, w // 4), max(1, h // 4)))
        arr = np.array(small, dtype=np.float32)

    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    brightness = (r + g + b) / 3
    blueish = (b - r) > 6
    bright_enough = brightness > 110
    sky_like = blueish & bright_enough

    if sky_like[: max(1, sky_like.shape[0] // 3)].mean() < 0.12:
        return False  # not enough confident sky near the top to bother

    labeled, n = ndimage.label(sky_like)
    if n == 0:
        return False
    top_labels = set(labeled[0][labeled[0] > 0].tolist())
    if not top_labels:
        return False
    sizes = {lbl: (labeled == lbl).sum() for lbl in top_labels}
    best = max(sizes, key=sizes.get)
    mask_small = labeled == best

    coverage = mask_small.mean()
    if coverage < 0.05 or coverage > 0.55:
        return False  # too small to matter, or too large to trust as "sky only"

    mask_img = Image.fromarray((mask_small * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=max(w, h) * 0.016))

    with Image.open(image_path) as im:
        rgba = im.convert("RGBA")
        rgba.putalpha(mask_img)
    rgba.save(out_png)
    return True


# ---------------------------------------------------------------------------
# Per-shot clip rendering
# ---------------------------------------------------------------------------

def build_image_clip(
    shot: Shot, index: int, work_dir: Path, cfg: Config,
    serif_font: str, sans_font: str, is_opener: bool, is_closer: bool,
) -> Path:
    out_path = work_dir / f"clip_{index:02d}.mp4"
    frames = max(1, int(shot.duration * FPS))
    zoom, x, y = _zoom_x_y(shot.motion, shot.focal_x, shot.focal_y, cfg.max_zoom, frames)
    base_chain = _zoompan_chain(zoom, x, y, frames)

    text_filters = typography.drawtext_filters(
        is_opener=is_opener, is_closer=is_closer, caption=shot.caption,
        property_name=cfg.property_name, location=cfg.location, cta=cfg.cta,
        duration=shot.duration, serif_font=serif_font, sans_font=sans_font,
    )
    text_chain = ("," + ",".join(text_filters)) if text_filters else ""

    sky_png = work_dir / f"sky_{index:02d}.png"
    use_sky = shot.sky_parallax and make_sky_cutout(Path(shot.path), sky_png)

    if not use_sky:
        run([
            "ffmpeg", "-y", "-loop", "1", "-i", shot.path, "-t", str(shot.duration),
            "-vf", base_chain + text_chain,
            "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
            str(out_path),
        ])
        return out_path

    # damped zoom/pan rate for the sky layer -> real differential parallax
    # (the far layer travels ~45% as far/fast as the foreground) on every
    # motion type, not just pans. The feathered alpha edge absorbs the
    # resulting sub-pixel drift at the horizon seam.
    sky_x_fx = _dampen(shot.focal_x, 0.45)
    sky_y_fx = _dampen(shot.focal_y, 0.45)
    sky_zoom, sky_x, sky_y = _zoom_x_y(shot.motion, sky_x_fx, sky_y_fx, cfg.max_zoom, frames, zoom_damp=0.45)
    sky_chain = _zoompan_chain(sky_zoom, sky_x, sky_y, frames)

    filter_complex = (
        f"[0:v]{base_chain},format=yuv420p[base];"
        f"[1:v]{sky_chain},format=rgba[sky];"
        f"[base][sky]overlay=format=auto{text_chain}[outv]"
    )
    run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", shot.path, "-t", str(shot.duration),
        "-loop", "1", "-i", str(sky_png), "-t", str(shot.duration),
        "-filter_complex", filter_complex, "-map", "[outv]",
        "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
        str(out_path),
    ])
    return out_path


def build_video_clip(
    shot: Shot, index: int, work_dir: Path, cfg: Config,
    serif_font: str, sans_font: str, is_opener: bool, is_closer: bool,
) -> Path:
    out_path = work_dir / f"clip_{index:02d}.mp4"
    text_filters = typography.drawtext_filters(
        is_opener=is_opener, is_closer=is_closer, caption=shot.caption,
        property_name=cfg.property_name, location=cfg.location, cta=cfg.cta,
        duration=shot.duration, serif_font=serif_font, sans_font=sans_font,
    )
    text_chain = ("," + ",".join(text_filters)) if text_filters else ""
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}{text_chain}"
    )
    # start 0.5s in to skip handheld start-shake if the clip is long enough
    start = 0.5 if shot.duration + 1.0 <= 8.0 else 0.0
    run([
        "ffmpeg", "-y", "-ss", str(start), "-i", shot.path, "-t", str(shot.duration),
        "-vf", vf, "-r", str(FPS), "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
        str(out_path),
    ])
    return out_path


def build_clip(shot: Shot, index: int, total: int, work_dir: Path, cfg: Config, serif_font: str, sans_font: str) -> Path:
    is_opener = index == 0
    is_closer = index == total - 1
    if shot.kind == "video":
        return build_video_clip(shot, index, work_dir, cfg, serif_font, sans_font, is_opener, is_closer)
    return build_image_clip(shot, index, work_dir, cfg, serif_font, sans_font, is_opener, is_closer)
