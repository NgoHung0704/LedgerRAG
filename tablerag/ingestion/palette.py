"""What colours a figure actually uses, and what to call them.

Colour coding is meaning that exists nowhere in a text layer: a risk scale
where the only signal is which of seven cells is filled, a status column that
says "conforme" by being green, a legend that pairs a swatch with a category.
Someone looking for it asks for "la zone rouge" — so the words "zone" and
"rouge" have to be in the index, and they have to be the RIGHT words.

Two halves, and only the first can be made exact:

  - WHICH colours are on the figure is measurable. A vector drawing states its
    fills; a raster one can be quantised. Both give an area-weighted palette.
  - WHAT a colour MEANS is on the legend, and only a model can read that. The
    palette is handed to it as evidence, the way the text-layer grid is, so it
    names a colour the same way twice instead of calling one fill "teal",
    "cyan" and "blue-green" in three descriptions.

Naming is done in CIELAB, not RGB. RGB distance is not perceptual — it will
call a vivid red "orange" and a document's blue "purple" — and a name that
moves between documents is worse than no name, because retrieval is exactly
what it is for. CIE76 (plain euclidean in Lab) is enough against a lexicon
this coarse; CIEDE2000 would matter for matching paint, not for choosing
between "rouge" and "orange".

The lexicon is deliberately the BASIC colour terms. "Rouge brique" is more
accurate and less findable: a reader asks with the word they know.
"""

from __future__ import annotations

import io

# representative sRGB for each basic term, with the words a reader would use
_LEXICON: list[tuple[tuple[int, int, int], dict[str, str]]] = [
    ((211, 47, 47), {"fr": "rouge", "en": "red"}),
    ((245, 124, 0), {"fr": "orange", "en": "orange"}),
    ((251, 192, 45), {"fr": "jaune", "en": "yellow"}),
    ((56, 142, 60), {"fr": "vert", "en": "green"}),
    ((0, 151, 167), {"fr": "turquoise", "en": "teal"}),
    ((25, 118, 210), {"fr": "bleu", "en": "blue"}),
    ((123, 31, 162), {"fr": "violet", "en": "purple"}),
    ((233, 30, 99), {"fr": "rose", "en": "pink"}),
    ((109, 76, 65), {"fr": "marron", "en": "brown"}),
    ((215, 204, 200), {"fr": "beige", "en": "beige"}),
    ((158, 158, 158), {"fr": "gris", "en": "grey"}),
    ((33, 33, 33), {"fr": "noir", "en": "black"}),
    ((250, 250, 250), {"fr": "blanc", "en": "white"}),
]

_QUALIFIER = {"fr": ("foncé", "clair"), "en": ("dark", "light")}
_NEUTRAL = {"gris", "noir", "blanc", "beige", "grey", "black", "white"}
# below this share of the figure a colour is a rounding error, not a code
_MIN_SHARE = 0.02


def _to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """sRGB (0-255) to CIELAB under D65 — the space where equal numeric
    distance means roughly equal perceived difference."""
    def linear(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.00000
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


_LEXICON_LAB = [(_to_lab(rgb), words) for rgb, words in _LEXICON]


def name_colour(rgb: tuple[int, int, int], locale: str | None = None) -> str:
    """The basic colour term for this sRGB value, in the document's language.

    A lightness qualifier is added for non-neutral colours, because "rouge
    foncé" and "rouge clair" are both things people search for — but never for
    grey, black or white, where it would say nothing."""
    lang = (locale or "en").strip().lower()[:2]
    if lang not in ("fr", "en"):
        lang = "en"
    lab = _to_lab(rgb)
    best = min(_LEXICON_LAB,
               key=lambda entry: sum((a - b) ** 2
                                     for a, b in zip(lab, entry[0])))
    name = best[1].get(lang, best[1]["en"])
    if name in _NEUTRAL:
        return name
    dark, light = _QUALIFIER[lang]
    if lab[0] < 35:
        return f"{name} {dark}"
    if lab[0] > 75:
        return f"{name} {light}"
    return name


def _tally(counted: list[tuple[tuple[int, int, int], float]],
           locale: str | None) -> list[tuple[str, str, float]]:
    """Area-weighted palette as (name, hex, share), most used first."""
    total = sum(weight for _, weight in counted)
    if total <= 0:
        return []
    by_name: dict[str, list] = {}
    for rgb, weight in counted:
        name = name_colour(rgb, locale)
        entry = by_name.setdefault(name, [0.0, rgb])
        entry[0] += weight
        if weight > 0:            # keep the hex of the largest area
            pass
    out = []
    for name, (weight, rgb) in by_name.items():
        share = weight / total
        if share >= _MIN_SHARE:
            out.append((name, "#%02x%02x%02x" % rgb, share))
    return sorted(out, key=lambda item: -item[2])


def vector_palette(page, bbox, locale: str | None = None
                   ) -> list[tuple[str, str, float]]:
    """Colours of a drawn figure, weighted by the area each one covers.

    Taken from the PDF's own fill and stroke operators, so it is exact: no
    quantisation, no anti-aliasing, no JPEG noise."""
    import fitz

    box = fitz.Rect(bbox)
    counted: list[tuple[tuple[int, int, int], float]] = []
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing["rect"]) & box
        if rect.is_empty:
            continue
        paint = drawing.get("fill") or drawing.get("color")
        if not paint:
            continue
        area = max(rect.get_area(), 1.0)
        counted.append((tuple(int(round(c * 255)) for c in paint[:3]), area))
    return _tally(counted, locale)


def raster_palette(png: bytes, locale: str | None = None, colours: int = 8
                   ) -> list[tuple[str, str, float]]:
    """Colours of a photographed or pasted figure, by quantising it.

    Median cut rather than k-means: it is deterministic, it is in Pillow
    already, and the answer only has to be stable enough to name."""
    from PIL import Image

    try:
        image = Image.open(io.BytesIO(png)).convert("RGB")
    except Exception:  # noqa: BLE001 — a figure must never fail a document
        return []
    image.thumbnail((256, 256))
    quantised = image.quantize(colors=colours, method=Image.MEDIANCUT)
    palette = quantised.getpalette() or []
    counted = [((palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]),
                float(count))
               for count, i in quantised.getcolors() or []
               if (i + 1) * 3 <= len(palette)]
    return _tally(counted, locale)


def describe_palette(palette: list[tuple[str, str, float]]) -> str:
    """The palette as one line for a prompt and for the index."""
    if not palette:
        return ""
    return ", ".join(f"{name} ({hexcode}, {share:.0%})"
                     for name, hexcode, share in palette)


def is_colour_coded(palette: list[tuple[str, str, float]]) -> bool:
    """Does colour look like it is CARRYING something here?

    Two or more inks on the page, counting GREY. Business charts code with
    grey against one accent far more often than with a rainbow — the
    factsheet's sector chart is exactly that, portfolio in turquoise against
    benchmark in grey, and a test that dismissed grey as neutral called the
    clearest colour-coded figure in the corpus uncoded.

    White alone is excluded: that is the paper, not a code."""
    inks = [name for name, _, _ in palette if name not in ("blanc", "white")]
    return len(inks) >= 2
