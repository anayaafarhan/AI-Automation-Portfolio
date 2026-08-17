"""Restrained premium typography: a title card, sparse amenity callouts, and
a closing CTA. Deliberately not a caption on every shot — the brief was
"do not overcrowd the video with text."
"""
from __future__ import annotations

from pathlib import Path

FONT_SERIF_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
]
FONT_SANS_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def find_font(candidates: list[str], override: str | None) -> str:
    if override and Path(override).exists():
        return override
    for f in candidates:
        if Path(f).exists():
            return f
    raise SystemExit(f"No usable font found among {candidates}. Pass --font.")


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("'", "\u2019").replace(":", "\\:").replace(",", "\\,")


def _fade_alpha(dur: float, fade: float = 0.5, hold_start: float = 0.0, hold_end: float | None = None) -> str:
    hold_end = dur if hold_end is None else hold_end
    return (
        f"if(lt(t\\,{hold_start})\\,0\\,"
        f"if(lt(t\\,{hold_start+fade})\\,(t-{hold_start})/{fade}\\,"
        f"if(lt(t\\,{hold_end-fade})\\,1\\,"
        f"if(lt(t\\,{hold_end})\\,({hold_end}-t)/{fade}\\,0))))"
    )


def drawtext_filters(
    *, is_opener: bool, is_closer: bool, caption: str,
    property_name: str, location: str, cta: str,
    duration: float, serif_font: str, sans_font: str,
) -> list[str]:
    """Returns a list of ffmpeg drawtext filter strings to chain for one shot."""
    filters = []

    if is_opener and (property_name or location):
        alpha = _fade_alpha(duration, fade=0.6, hold_start=0.15, hold_end=min(duration, 3.0))
        if property_name:
            name = _esc(property_name.upper())
            filters.append(
                f"drawtext=fontfile='{serif_font}':text='{name}':"
                f"fontcolor=white:fontsize=76:x=(w-text_w)/2:y=(h/2)-70:"
                f"shadowcolor=black@0.6:shadowx=0:shadowy=3:alpha='{alpha}'"
            )
        if location:
            loc = _esc(location.upper())
            filters.append(
                f"drawtext=fontfile='{sans_font}':text='{loc}':"
                f"fontcolor=white@0.9:fontsize=34:x=(w-text_w)/2:y=(h/2)+20:"
                f"shadowcolor=black@0.6:shadowx=0:shadowy=2:alpha='{alpha}'"
            )

    if caption and not is_opener:
        alpha = _fade_alpha(duration, fade=0.5, hold_start=0.25, hold_end=duration - 0.25)
        text = _esc(caption.upper())
        # thin underline accent instead of a solid caption box — reads as
        # editorial titling rather than an informational slideshow label
        filters.append(
            f"drawtext=fontfile='{sans_font}':text='{text}':"
            f"fontcolor=white:fontsize=42:x=(w-text_w)/2:y=h-300:"
            f"shadowcolor=black@0.65:shadowx=0:shadowy=2:alpha='{alpha}'"
        )
        filters.append(
            f"drawbox=x=(w-260)/2:y=h-300+58:w=260:h=2:color=white@0.85:t=fill:"
            f"enable='between(t\\,0.25\\,{duration-0.25})'"
        )

    if is_closer and cta:
        alpha = _fade_alpha(duration, fade=0.6, hold_start=max(duration - 2.4, 0.0), hold_end=duration)
        text = _esc(cta.upper())
        filters.append(
            f"drawtext=fontfile='{serif_font}':text='{text}':"
            f"fontcolor=white:fontsize=58:x=(w-text_w)/2:y=h-420:"
            f"shadowcolor=black@0.6:shadowx=0:shadowy=3:alpha='{alpha}'"
        )
        filters.append(
            f"drawbox=x=(w-140)/2:y=h-420+72:w=140:h=2:color=white@0.85:t=fill:"
            f"enable='gte(t\\,{max(duration-2.4,0.0)})'"
        )

    return filters
