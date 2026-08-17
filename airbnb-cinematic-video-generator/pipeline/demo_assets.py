"""Generates a synthetic sample property photo set for --demo mode.

These are clearly-synthetic stand-ins (gradients + simple shapes), not
photos of a real place — good enough to exercise every stage of the
pipeline (including the sky-parallax path) so a prospective client can see
the finished pacing/grade/typography/motion before you point it at real
listing photos.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1600, 1200


def _sky_gradient(draw_img: Image.Image, top, bottom, height_frac=0.55):
    w, h = draw_img.size
    sky_h = int(h * height_frac)
    for y in range(sky_h):
        t = y / max(sky_h - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        ImageDraw.Draw(draw_img).line([(0, y), (w, y)], fill=color)
    return sky_h


def _ground_gradient(img: Image.Image, y0: int, top, bottom):
    w, h = img.size
    d = ImageDraw.Draw(img)
    for y in range(y0, h):
        t = (y - y0) / max(h - y0 - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=color)


def make_exterior(path: Path, seed: int) -> None:
    random.seed(seed)
    img = Image.new("RGB", (W, H))
    horizon = _sky_gradient(img, (140, 190, 240), (225, 235, 245), 0.5)
    _ground_gradient(img, horizon, (190, 175, 150), (140, 120, 95))
    d = ImageDraw.Draw(img)
    # simple villa silhouette
    body = [(int(W*0.2), horizon), (int(W*0.8), horizon), (int(W*0.8), int(H*0.78)), (int(W*0.2), int(H*0.78))]
    d.polygon(body, fill=(235, 225, 205))
    d.polygon([(int(W*0.15), horizon), (int(W*0.5), int(horizon-H*0.12)), (int(W*0.85), horizon)], fill=(160, 90, 70))
    for i in range(4):
        x0 = int(W*0.28) + i * int(W*0.12)
        d.rectangle([x0, int(horizon+H*0.08), x0+int(W*0.07), int(horizon+H*0.22)], fill=(90, 130, 170))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img.save(path, quality=92)


def make_pool(path: Path, seed: int) -> None:
    random.seed(seed)
    img = Image.new("RGB", (W, H))
    horizon = _sky_gradient(img, (120, 180, 235), (200, 225, 245), 0.42)
    _ground_gradient(img, horizon, (60, 150, 170), (20, 90, 120))
    d = ImageDraw.Draw(img)
    for i in range(30):
        y = horizon + random.randint(0, H - horizon)
        x0 = random.randint(0, W - 120)
        d.line([(x0, y), (x0 + 100, y)], fill=(120, 200, 210), width=2)
    d.rectangle([0, int(H*0.9), W, H], fill=(200, 190, 170))
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    img.save(path, quality=92)


def make_view(path: Path, seed: int) -> None:
    random.seed(seed)
    img = Image.new("RGB", (W, H))
    horizon = _sky_gradient(img, (255, 175, 120), (255, 225, 190), 0.6)
    _ground_gradient(img, horizon, (70, 90, 120), (30, 40, 60))
    d = ImageDraw.Draw(img)
    for i in range(6):
        x = int(W * (0.1 + i * 0.15))
        hgt = random.randint(int(H*0.05), int(H*0.15))
        d.polygon([(x, horizon), (x+int(W*0.05), horizon-hgt), (x+int(W*0.1), horizon)], fill=(60, 60, 80))
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img.save(path, quality=92)


def make_interior(path: Path, seed: int, warm=True) -> None:
    random.seed(seed)
    img = Image.new("RGB", (W, H))
    top = (60, 50, 45) if warm else (200, 205, 210)
    bottom = (150, 120, 90) if warm else (235, 235, 235)
    for y in range(H):
        t = y / (H - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        ImageDraw.Draw(img).line([(0, y), (W, y)], fill=color)
    d = ImageDraw.Draw(img)
    # a "window" hinting at sky, kept small so it never registers as a
    # dominant sky region for the parallax gate
    d.rectangle([int(W*0.62), int(H*0.15), int(W*0.92), int(H*0.55)], fill=(150, 190, 225))
    d.rectangle([int(W*0.62), int(H*0.15), int(W*0.92), int(H*0.55)], outline=(255, 255, 255), width=6)
    # simple furniture blocks
    d.rectangle([int(W*0.08), int(H*0.62), int(W*0.42), int(H*0.85)], fill=(90, 70, 60))
    d.rectangle([int(W*0.08), int(H*0.85), int(W*0.42), int(H*0.9)], fill=(60, 45, 40))
    for i in range(3):
        d.rectangle([int(W*0.1)+i*int(W*0.09), int(H*0.55), int(W*0.1)+i*int(W*0.09)+int(W*0.07), int(H*0.62)], fill=(200, 200, 205))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    # soft vignette for warmth
    img.save(path, quality=92)


DEMO_SPEC = [
    ("01_exterior.jpg", make_exterior),
    ("02_living_room.jpg", lambda p, s: make_interior(p, s, warm=True)),
    ("03_kitchen.jpg", lambda p, s: make_interior(p, s, warm=False)),
    ("04_bedroom.jpg", lambda p, s: make_interior(p, s, warm=True)),
    ("05_bathroom.jpg", lambda p, s: make_interior(p, s, warm=False)),
    ("06_pool.jpg", make_pool),
    ("07_view_terrace.jpg", make_view),
]


def generate_demo_assets(input_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    for i, (name, fn) in enumerate(DEMO_SPEC):
        fn(input_dir / name, 100 + i)
    print(f"  wrote {len(DEMO_SPEC)} synthetic demo photos to {input_dir}/")
