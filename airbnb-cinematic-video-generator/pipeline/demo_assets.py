"""Generates a synthetic sample property photo set for --demo mode.

These are clearly-synthetic stand-ins (gradients, soft light glows, and
silhouette compositions built with Pillow/numpy) — NOT photographs of a
real place, and not AI-generated. They exist to exercise every stage of
the pipeline (including the sky-parallax path) end to end so you can
evaluate the pacing/grade/typography/motion/sound design before pointing
the pipeline at real, licensed listing photos. See the README for why real
stock photography can't be fetched automatically in this environment.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1600, 1200


def _vgrad(size, top, bottom, y0=0, y1=None):
    w, h = size
    y1 = h if y1 is None else y1
    arr = np.zeros((h, w, 3), dtype=np.float32)
    span = max(y1 - y0, 1)
    for y in range(y0, min(y1, h)):
        t = (y - y0) / span
        arr[y, :] = [top[i] + (bottom[i] - top[i]) * t for i in range(3)]
    if y0 > 0:
        arr[:y0, :] = top
    if y1 < h:
        arr[y1:, :] = bottom
    return arr


def _radial_glow(canvas: np.ndarray, cx, cy, radius, color, strength=1.0):
    h, w, _ = canvas.shape
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / radius
    falloff = np.clip(1.0 - dist, 0, 1) ** 2 * strength
    for i in range(3):
        canvas[..., i] = canvas[..., i] + falloff * (color[i] - canvas[..., i]) * falloff
    return canvas


def _to_img(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _finalize(img: Image.Image, knee=186.0, ceiling=233.0) -> Image.Image:
    """Soft-knee highlight rolloff applied to the FINISHED raster (after all
    drawing, which uses hardcoded fills that bypass the numpy gradient/glow
    pipeline). Compresses everything above `knee` into [knee, ceiling]
    instead of letting it clip to flat white — controlled highlights, no
    blown-out patches, even under a tight push-in on a bright element."""
    arr = np.array(img).astype(np.float32)
    over = arr > knee
    arr[over] = knee + (arr[over] - knee) * ((ceiling - knee) / (255.0 - knee))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _soft_shadow_polygon(img, points, blur=18, alpha=70):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).polygon(points, fill=(0, 0, 0, alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(blur))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def make_exterior_hook(path: Path, seed: int) -> None:
    """0-3s hook: golden-hour hero establishing shot. Horizon kept low so
    the title card (rendered centered, roughly the middle third of frame)
    always sits over clean open sky, never fighting the roofline/windows."""
    random.seed(seed)
    sky = _vgrad((W, H), (55, 65, 105), (250, 175, 125), 0, int(H * 0.74))
    sky[int(H * 0.74):] = (235, 192, 152)
    sky = _radial_glow(sky, int(W * 0.62), int(H * 0.30), W * 0.55, (255, 235, 190), 0.9)
    img = _to_img(sky)
    d = ImageDraw.Draw(img)
    horizon = int(H * 0.74)
    # low-rise villa silhouette with clean modern roofline, kept in the
    # lower third so it never competes with the title card
    d.polygon([(int(W*0.1), horizon), (int(W*0.9), horizon), (int(W*0.9), int(H*0.58)),
               (int(W*0.72), int(H*0.54)), (int(W*0.72), int(H*0.5)), (int(W*0.38), int(H*0.5)),
               (int(W*0.38), int(H*0.58)), (int(W*0.1), int(H*0.58))], fill=(28, 24, 28))
    for i in range(5):
        x0 = int(W*0.16) + i * int(W*0.12)
        d.rectangle([x0, int(H*0.61), x0+int(W*0.07), int(H*0.71)], fill=(250, 205, 135))
    # infinity pool foreground strip reflecting the sky
    pool = _vgrad((W, H - horizon), (150, 190, 200), (70, 120, 140))
    img.paste(_to_img(pool), (0, horizon))
    d = ImageDraw.Draw(img)
    for _ in range(12):
        x0 = random.randint(0, W-120)
        y = horizon + random.randint(15, H - horizon - 15)
        d.line([(x0, y), (x0+100, y)], fill=(215, 232, 228), width=1)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img = _finalize(img)
    img.save(path, quality=93)


def make_interior_arrival(path: Path, seed: int) -> None:
    """3-7s: bright, airy entry, welcoming daylight — furnished enough that
    a tight push-in always lands on something with detail, never a blank
    wall."""
    random.seed(seed)
    floor_y = int(H*0.78)
    base = _vgrad((W, floor_y), (228, 219, 203), (208, 196, 174), 0, floor_y)
    floor = _vgrad((W, H-floor_y), (150, 128, 100), (110, 92, 72))
    arr = np.vstack([base, floor])
    win = (int(W*0.56), int(H*0.12), int(W*0.92), int(H*0.6))
    arr = _radial_glow(arr, int((win[0]+win[2])/2), int((win[1]+win[3])/2), W*0.3, (250, 244, 230), 0.55)
    img = _to_img(arr)
    d = ImageDraw.Draw(img)
    d.rectangle(win, outline=(255, 255, 255), width=8)
    d.line([(int((win[0]+win[2])/2), win[1]), (int((win[0]+win[2])/2), win[3])], fill=(255, 255, 255), width=6)
    # hint of greenery visible through the window
    d.ellipse([win[0]+30, win[3]-140, win[0]+150, win[3]-20], fill=(95, 130, 90))
    # console table + a tall vase, soft shadow beneath both
    d.rectangle([int(W*0.08), int(H*0.62), int(W*0.36), int(H*0.7)], fill=(78, 58, 44))
    d.rectangle([int(W*0.11), int(H*0.46), int(W*0.14), int(H*0.62)], fill=(50, 46, 40))
    d.ellipse([int(W*0.095), int(H*0.42), int(W*0.155), int(H*0.48)], fill=(90, 110, 80))
    _soft_shadow_polygon(img, [(int(W*0.08), int(H*0.7)), (int(W*0.36), int(H*0.7)),
                                (int(W*0.38), int(H*0.76)), (int(W*0.06), int(H*0.76))])
    # a low bench/ottoman on the right for balance
    d.rounded_rectangle([int(W*0.42), int(H*0.68), int(W*0.56), int(H*0.76)], radius=10, fill=(120, 100, 80))
    # rug
    d.rounded_rectangle([int(W*0.06), int(H*0.82), int(W*0.62), int(H*0.95)], radius=8, fill=(178, 160, 138))
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img = _finalize(img)
    img.save(path, quality=93)


def make_living_space(path: Path, seed: int) -> None:
    """7-11s: lounge/living space, warm lamp light, evening comfort —
    brighter and higher-contrast than a first pass so the sofa reads
    clearly against the wall instead of dissolving into it."""
    random.seed(seed)
    floor_y = int(H*0.86)
    base = _vgrad((W, floor_y), (68, 56, 50), (100, 82, 64), 0, floor_y)
    floor = _vgrad((W, H-floor_y), (58, 46, 38), (36, 28, 24))
    arr = np.vstack([base, floor])
    arr = _radial_glow(arr, int(W*0.24), int(H*0.42), W*0.3, (255, 195, 130), 0.8)
    arr = _radial_glow(arr, int(W*0.82), int(H*0.2), W*0.35, (130, 150, 170), 0.3)
    img = _to_img(arr)
    d = ImageDraw.Draw(img)
    # rug under the seating area
    d.rounded_rectangle([int(W*0.02), int(H*0.78), int(W*0.58), int(H*0.92)], radius=8, fill=(90, 66, 52))
    # sofa silhouette, lighter than the wall so it reads clearly
    d.rounded_rectangle([int(W*0.06), int(H*0.58), int(W*0.5), int(H*0.82)], radius=22, fill=(150, 118, 92))
    d.rounded_rectangle([int(W*0.06), int(H*0.52), int(W*0.16), int(H*0.62)], radius=14, fill=(150, 118, 92))
    d.rounded_rectangle([int(W*0.4), int(H*0.52), int(W*0.5), int(H*0.62)], radius=14, fill=(150, 118, 92))
    # coffee table + a small warm lamp accent
    d.rounded_rectangle([int(W*0.16), int(H*0.72), int(W*0.34), int(H*0.79)], radius=6, fill=(45, 36, 30))
    d.ellipse([int(W*0.235), int(H*0.66), int(W*0.265), int(H*0.72)], fill=(255, 210, 150))
    # window with dusk view, softened rather than a flat block
    win = (int(W*0.62), int(H*0.16), int(W*0.94), int(H*0.56))
    win_view = _vgrad((win[2]-win[0], win[3]-win[1]), (90, 105, 130), (55, 65, 90))
    img.paste(_to_img(win_view), (win[0], win[1]))
    d.rectangle(win, outline=(28, 24, 22), width=10)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img = _finalize(img)
    img.save(path, quality=93)


def make_pool(path: Path, seed: int) -> None:
    """11-15s: pool / outdoor experience, bright blue-sky daylight."""
    random.seed(seed)
    sky = _vgrad((W, int(H*0.42)), (110, 175, 232), (195, 220, 240))
    water = _vgrad((W, H - int(H*0.42)), (55, 150, 165), (15, 90, 110))
    arr = np.vstack([sky, water])
    arr = _radial_glow(arr, int(W*0.75), int(H*0.12), W*0.3, (255, 250, 235), 0.7)
    img = _to_img(arr)
    d = ImageDraw.Draw(img)
    horizon = int(H*0.42)
    for _ in range(26):
        y = horizon + random.randint(10, H - horizon - 10)
        x0 = random.randint(0, W-140)
        shade = random.randint(180, 235)
        d.line([(x0, y), (x0+120, y)], fill=(shade, shade+8, shade+5), width=2)
    d.rectangle([0, int(H*0.94), W, H], fill=(220, 205, 180))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    img = _finalize(img)
    img.save(path, quality=93)


def make_bedroom(path: Path, seed: int) -> None:
    """15-19s: bedroom / comfort, soft warm evening light. Linen tones
    instead of near-white — a tight push-in on the bed should still read as
    "fabric with texture," not a blown-out white void."""
    random.seed(seed)
    floor_y = int(H*0.88)
    base = _vgrad((W, floor_y), (58, 48, 50), (98, 78, 68), 0, floor_y)
    floor = _vgrad((W, H-floor_y), (55, 44, 40), (34, 27, 25))
    arr = np.vstack([base, floor])
    arr = _radial_glow(arr, int(W*0.2), int(H*0.32), W*0.28, (240, 190, 145), 0.65)
    img = _to_img(arr)
    d = ImageDraw.Draw(img)
    # bed frame + linen (warm taupe, not white) + a contrasting throw
    d.rounded_rectangle([int(W*0.14), int(H*0.56), int(W*0.76), int(H*0.84)], radius=20, fill=(196, 176, 152))
    d.rounded_rectangle([int(W*0.14), int(H*0.5), int(W*0.76), int(H*0.62)], radius=18, fill=(214, 197, 176))
    for i in range(2):
        d.rounded_rectangle([int(W*0.17)+i*int(W*0.24), int(H*0.5), int(W*0.17)+i*int(W*0.24)+int(W*0.17), int(H*0.58)],
                             radius=12, fill=(225, 212, 195))
    d.rounded_rectangle([int(W*0.14), int(H*0.72), int(W*0.76), int(H*0.8)], radius=14, fill=(150, 88, 62))
    # nightstand + lamp glow
    d.rectangle([int(W*0.78), int(H*0.66), int(W*0.9), int(H*0.82)], fill=(60, 48, 40))
    d.ellipse([int(W*0.795), int(H*0.58), int(W*0.885), int(H*0.68)], fill=(235, 195, 145))
    # window, night glow — kept modest, not a flat bright block
    win = (int(W*0.8), int(H*0.16), int(W*0.95), int(H*0.4))
    win_view = _vgrad((win[2]-win[0], win[3]-win[1]), (55, 65, 95), (35, 40, 65))
    img.paste(_to_img(win_view), (win[0], win[1]))
    d.rectangle(win, outline=(30, 25, 24), width=8)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img = _finalize(img)
    img.save(path, quality=93)


def make_hero_sunset(path: Path, seed: int) -> None:
    """19-24s: hero exterior / sunset / destination, the emotional peak."""
    random.seed(seed)
    sky = _vgrad((W, H), (35, 30, 60), (255, 140, 95), 0, int(H*0.68))
    sky[int(H*0.68):] = (40, 45, 70)
    arr = _radial_glow(sky, int(W*0.5), int(H*0.6), W*0.45, (255, 210, 150), 1.0)
    img = _to_img(arr)
    d = ImageDraw.Draw(img)
    horizon = int(H*0.68)
    d.ellipse([int(W*0.5)-90, horizon-90, int(W*0.5)+90, horizon+90], fill=(255, 225, 180))
    for i in range(3):
        x = int(W*(0.15+i*0.32))
        hgt = random.randint(int(H*0.06), int(H*0.14))
        d.polygon([(x, horizon), (x+int(W*0.05), horizon-hgt), (x+int(W*0.1), horizon)], fill=(22, 18, 30))
    # water reflection strip
    refl = _vgrad((W, H-horizon), (120, 90, 90), (30, 26, 40))
    img.paste(_to_img(refl), (0, horizon))
    for _ in range(8):
        x0 = random.randint(0, W-100)
        y = horizon + random.randint(10, H-horizon-10)
        d.line([(x0, y), (x0+80, y)], fill=(200, 150, 130), width=1)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img = _finalize(img)
    img.save(path, quality=93)


DEMO_SPEC = [
    ("01_exterior.jpg", make_exterior_hook),
    ("02_living_room.jpg", make_interior_arrival),
    ("03_dining_area.jpg", make_living_space),
    ("04_pool.jpg", make_pool),
    ("05_bedroom.jpg", make_bedroom),
    ("06_view_terrace.jpg", make_hero_sunset),
]


def generate_demo_assets(input_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    for i, (name, fn) in enumerate(DEMO_SPEC):
        fn(input_dir / name, 100 + i)
    print(f"  wrote {len(DEMO_SPEC)} synthetic demo photos to {input_dir}/")
