"""Render the pinned demo timeline into the shipped video assets.

``scripts/make_demo.py`` pins *what* the demo says and *when* each line
lands; this script pins *how it moves as a movie*:

* ``docs/demo.mp4``        — 1920x1080, silent H.264 (yuv420p, faststart):
                             the 30-second terminal demo plus a short
                             branded end card. For X, Reddit, HN showcases.
* ``docs/demo.gif``        — 960x540, 15 fps palette GIF of the same
                             timeline, for READMEs and chat contexts.
* ``docs/demo-poster.png`` — the finished terminal frame, for thumbnails.
* ``docs/demo.video.json`` — manifest (dimensions, durations, line times,
                             sha256 of each file); ``--check`` verifies the
                             shipped binaries against it, and
                             ``tests/test_demo_video.py`` fails the build
                             on drift — exactly like the cast/SVG pair.

Generated output — never edit by hand. Regenerate with
``python scripts/make_video.py`` (needs Pillow + ffmpeg). ``--check``
needs neither Pillow nor a re-render; ``--probe OUT.png --at SECONDS``
renders one frame for inspection (Pillow only, no ffmpeg).

The timeline is NOT redefined here: line times come from
``make_demo.schedule()`` over the live ``examples/demo.py`` transcript, so
cast, SVG and video can never disagree — the test suite asserts it.

The end card composites ``Logo-Designs/aegis-zero-logo.png``, rasterized
once from the committed SVG (its background is pure black, matching the
card, so the plate composites seamlessly):

    ffmpeg -i Logo-Designs/aegis-zero-logo.svg -vf scale=1280:-1 \
        -frames:v 1 Logo-Designs/aegis-zero-logo.png
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from importlib import util as importlib_util
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — annotations only
    from PIL import Image as PilImage

try:  # Pillow is a *render-time* tool: the module stays importable without it
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    """Import a repo file by path (examples/ and scripts/ are not packages)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib_util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


make_demo = _load("make_demo", REPO / "scripts" / "make_demo.py")
demo = sys.modules["demo"]  # loaded by make_demo

# ------------------------------------------------------------- timeline
# Every appearance time below is inherited from the pinned schedule — the
# same numbers that ship inside docs/demo.cast and docs/demo.svg.
TIMED, TERMINAL_DURATION = make_demo.schedule(make_demo.transcript())
LINE_TIMES = [time for _, time in TIMED]
ROWS = len(TIMED) + 1  # transcript rows + the closing prompt row
CLOSING_T0 = LINE_TIMES[-1]

FADE = 0.45  # mirrors the SVG's aegis-in .45s ease-out
TYPE_SECONDS = 1.2  # typewriter window for the command line
CROSSFADE = 0.6  # finished terminal -> end card
ENDCARD = 3.5
TOTAL = round(TERMINAL_DURATION + CROSSFADE + ENDCARD, 2)
FRAMES = round(TOTAL * 30)
POSTER_T = round(TERMINAL_DURATION - 0.05, 2)  # all lines visible, cursor ON

# --------------------------------------------------------------- layout
WIDTH, HEIGHT = 1920, 1080  # 16:9: safe everywhere socials live
FPS = 30
WINDOW_W = 1280
TITLE_H = 64
GAP_TOP = 14
LINE_H = 41
BOTTOM_PAD = 18
PAD_X = 64
FONT_MONO = 27
TITLE_TEXT = "aegis-zero — offline demo"

# Terminal chrome + line colours reuse the SVG palette exactly.
FG = make_demo.FG
PROMPT_GREEN = "#3fb950"
INK = "#e6edf3"
MUTED = "#8b949e"
OUTER_BG = "#05070b"
CHROME_BG = "#0d1117"
TITLE_BG = "#161b22"
BORDER = "#30363d"
BRAND_CYAN = "#00ffcc"  # Logo-Designs/BRANDING.md

# End card (pure #000000: the logo PNG's own background, so it merges).
ENDCARD_BG = "#000000"
LOGO_H = 420  # display height of the logo art (after margin-cropping)
CHIP_FONT = 30
LINK_FONT = 28
TAGLINE_FONT = 24
CHIP_STAGGER, LINK_STAGGER, TAGLINE_STAGGER = 0.5, 0.9, 1.3

MONO_CANDIDATES = [
    Path.home() / ".local/share/fonts/JetBrains/JetBrainsMonoNerdFont-Regular.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    Path("/usr/share/fonts/liberation/LiberationMono-Regular.ttf"),
]
SANS_CANDIDATES = [
    Path("/usr/share/fonts/noto/NotoSans-Regular.ttf"),
    Path("/usr/share/fonts/liberation/LiberationSans-Regular.ttf"),
]

ASSETS = ("docs/demo.mp4", "docs/demo.gif", "docs/demo-poster.png")
MANIFEST = "docs/demo.video.json"
LOGO = "Logo-Designs/aegis-zero-logo.png"


def _rgb(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = color.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def _ease(fraction: float) -> float:
    """SVG-style ease-out (cubic-bezier(0,0,0.58,1) ≈ quadratic)."""
    if fraction <= 0:
        return 0.0
    if fraction >= 1:
        return 1.0
    return 1.0 - (1.0 - fraction) ** 2


# ----------------------------------------------------------------- fonts
_FONTS: dict[tuple[str, int], Any] = {}
_FONT_NAMES: dict[str, str] = {}


def _font(role: str, size: int) -> Any:
    if (role, size) not in _FONTS:
        candidates = MONO_CANDIDATES if role == "mono" else SANS_CANDIDATES
        for path in candidates:
            if path.is_file():
                assert ImageFont is not None
                _FONTS[(role, size)] = ImageFont.truetype(str(path), size)
                _FONT_NAMES[role] = path.name
                break
        else:
            names = ", ".join(str(path) for path in candidates)
            raise RuntimeError(f"no {role} font found — looked in: {names}")
    return _FONTS[(role, size)]


def font_name(role: str) -> str:
    """Name of the resolved font file (recorded in the manifest)."""
    _font(role, FONT_MONO if role == "mono" else LINK_FONT)
    return _FONT_NAMES[role]


def _advance() -> float:
    """Width of one monospace cell at the demo font size."""
    return _font("mono", FONT_MONO).getlength("0")


# ------------------------------------------------------------ resources
class _Res:
    """Every pre-rendered PIL object the frame compositor needs."""

    def __init__(self) -> None:
        assert Image is not None and ImageDraw is not None
        mono = _font("mono", FONT_MONO)
        self.advance = _advance()
        self.ascent, self.descent = mono.getmetrics()

        self.win_x = (WIDTH - WINDOW_W) // 2
        self.window_h = TITLE_H + GAP_TOP + ROWS * LINE_H + BOTTOM_PAD
        self.win_y = (HEIGHT - self.window_h) // 2

        self.chrome = self._build_chrome()
        self.lines = [
            self._line_sprite(i, kind, text)
            for i, ((kind, text), _t0) in enumerate(TIMED)  # items: ((kind, text), time)
        ]
        cmd_text = next(text for (kind, text), _t in TIMED if kind == "cmd")
        self.type_x = [round(mono.getlength(cmd_text[:n])) for n in range(len(cmd_text) + 1)]
        self.closing = self._closing_row()
        self.endcard = self._build_endcard()

    # -- geometry -------------------------------------------------------
    def baseline(self, row: int) -> int:
        """Y coordinate of a text baseline, in frame space."""
        return self.win_y + TITLE_H + GAP_TOP + self.ascent + row * LINE_H

    def row_center_y(self, row: int) -> int:
        """Mid-height of a row (probe/test helper)."""
        return self.baseline(row) - self.ascent // 2

    # -- chrome ---------------------------------------------------------
    def _build_chrome(self) -> PilImage.Image:
        """The static terminal window every frame starts from (SVG look)."""
        im = Image.new("RGBA", (WIDTH, HEIGHT), _rgb(OUTER_BG))
        d = ImageDraw.Draw(im)
        x0, y0, x1, y1 = (
            self.win_x,
            self.win_y,
            self.win_x + WINDOW_W,
            self.win_y + self.window_h,
        )
        d.rounded_rectangle(
            [x0, y0, x1, y1], radius=22, fill=_rgb(CHROME_BG), width=3, outline=_rgb(BORDER)
        )
        d.rounded_rectangle([x0, y0, x1, y0 + TITLE_H], radius=22, fill=_rgb(TITLE_BG))
        d.rectangle([x0, y0 + TITLE_H - 22, x1, y0 + TITLE_H], fill=_rgb(TITLE_BG))
        d.line([x0, y0 + TITLE_H, x1, y0 + TITLE_H], fill=_rgb(BORDER), width=3)
        for dx, color in ((34, "#ff5f56"), (74, "#ffbd2e"), (114, "#27c93f")):
            d.ellipse(
                [x0 + dx - 11, y0 + TITLE_H // 2 - 11, x0 + dx + 11, y0 + TITLE_H // 2 + 11],
                fill=_rgb(color),
            )
        title = _font("sans", 24)
        d.text(
            ((x0 + x1) // 2, y0 + TITLE_H // 2 - 1),
            TITLE_TEXT,
            font=title,
            fill=_rgb(MUTED),
            anchor="mm",
        )
        return im

    # -- line sprites ---------------------------------------------------
    def _line_sprite(
        self, row: int, kind: str, text: str, t0: float | None = None
    ) -> dict[str, Any]:
        """One transcript line at full opacity on a tight transparent sprite."""
        assert Image is not None and ImageDraw is not None
        mono = _font("mono", FONT_MONO)
        prompt_w = mono.getlength("$ ") if kind == "cmd" else 0.0
        width = math.ceil(prompt_w + mono.getlength(text)) + 2
        sprite = Image.new("RGBA", (width, self.ascent + self.descent + 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(sprite)
        if kind == "cmd":
            d.text((1, 1), "$", font=mono, fill=_rgb(PROMPT_GREEN))
            d.text((1 + prompt_w, 1), text, font=mono, fill=_rgb(FG[kind]))
        elif kind != "sp":  # spacer rows keep their slot but paint nothing
            d.text((1, 1), text, font=mono, fill=_rgb(FG[kind]))
        base = self.baseline(row)
        return {
            "kind": kind,
            "text": text,
            "t0": LINE_TIMES[row] if t0 is None else t0,
            "sprite": sprite,
            "x": self.win_x + PAD_X,
            "y": base - self.ascent,
            "prompt_w": prompt_w,
        }

    def _closing_row(self) -> dict[str, Any]:
        """The fresh prompt (' $ ▮') that closes the recording, as in the SVG."""
        # The SVG gives the closing prompt the LAST line's delay, not a new slot.
        return self._line_sprite(ROWS - 1, "cmd", "", t0=CLOSING_T0)

    # -- end card -------------------------------------------------------
    def _build_endcard(self) -> dict[str, Any]:
        logo = Image.open(REPO / LOGO).convert("RGBA")
        # The SVG canvas carries wide empty margins; crop to the art itself,
        # then size it by height so the card layout never depends on them.
        art = logo.convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
        assert art is not None
        logo = logo.crop(art)
        logo = logo.resize((round(logo.width * LOGO_H / logo.height), LOGO_H), Image.LANCZOS)

        chip_font = _font("mono", CHIP_FONT)
        chip_text = "pip install aegis-zero"
        prompt_w = chip_font.getlength("$ ")
        text_w = prompt_w + chip_font.getlength(chip_text)
        asc, desc = chip_font.getmetrics()
        pad_x, pad_y = 34, 20
        chip = Image.new(
            "RGBA", (int(text_w) + 2 * pad_x + 2, asc + desc + 2 * pad_y + 2), (0, 0, 0, 0)
        )
        cd = ImageDraw.Draw(chip)
        cd.rounded_rectangle(
            [1, 1, chip.width - 2, chip.height - 2],
            radius=18,
            fill=_rgb(CHROME_BG),
            outline=_rgb(BORDER),
            width=2,
        )
        cd.text((pad_x, pad_y), "$", font=chip_font, fill=_rgb(PROMPT_GREEN))
        cd.text((pad_x + prompt_w, pad_y), chip_text, font=chip_font, fill=_rgb(INK))

        link = _text_sprite("sans", LINK_FONT, "github.com/khalidhassan01/Aegis-Zero", MUTED)
        tagline = _text_sprite(
            "sans", TAGLINE_FONT, "offline · deterministic · auditable", BRAND_CYAN
        )

        logo_y = 140
        chip_y = logo_y + LOGO_H + 70
        link_y = chip_y + chip.height + 58
        tag_y = link_y + 66
        return {
            "logo": (logo, (WIDTH - logo.width) // 2, logo_y),
            "chip": (chip, (WIDTH - chip.width) // 2, chip_y),
            "link": (link, (WIDTH - link.width) // 2, link_y),
            "tagline": (tagline, (WIDTH - tagline.width) // 2, tag_y),
        }


def _text_sprite(role: str, size: int, text: str, color: str) -> PilImage.Image:
    assert Image is not None and ImageDraw is not None
    font = _font(role, size)
    asc, desc = font.getmetrics()
    sprite = Image.new(
        "RGBA", (math.ceil(font.getlength(text)) + 2, asc + desc + 2), (0, 0, 0, 0)
    )
    ImageDraw.Draw(sprite).text((1, 1), text, font=font, fill=_rgb(color))
    return sprite


_RES: _Res | None = None


def _resources() -> _Res:
    global _RES
    if _RES is None:
        if Image is None:
            raise RuntimeError(
                "Pillow is required to render frames — install it into the venv first"
            )
        _RES = _Res()
    return _RES


# --------------------------------------------------------------- frames
def _composite(
    im: PilImage.Image, sprite: PilImage.Image, xy: tuple[int, int], k: float
) -> None:
    """Source-over composite with a global fade factor (PIL fills replace)."""
    if k >= 1.0:
        im.alpha_composite(sprite, xy)
        return
    assert Image is not None
    faded = sprite.copy()
    faded.putalpha(faded.getchannel("A").point(lambda a: int(a * k)))
    im.alpha_composite(faded, xy)


def _cursor(im: PilImage.Image, x: int, baseline: int) -> None:
    """The block cursor, sized like the SVG's closing cursor."""
    assert ImageDraw is not None
    res = _resources()
    top = baseline - FONT_MONO + 4
    ImageDraw.Draw(im).rectangle(
        [x, top, x + int(res.advance), top + FONT_MONO - 2], fill=_rgb(INK)
    )


def _terminal_frame(t: float) -> PilImage.Image:
    res = _resources()
    im = res.chrome.copy()

    for i, line in enumerate(res.lines):
        if line["kind"] == "sp" or t < line["t0"]:
            continue
        if line["kind"] == "cmd" and t < line["t0"] + TYPE_SECONDS:
            progress = (t - line["t0"]) / TYPE_SECONDS
            typed = min(int(progress * len(line["text"])), len(line["text"]))
            cut = min(int(1 + line["prompt_w"]) + res.type_x[typed] + 1, line["sprite"].width)
            im.alpha_composite(
                line["sprite"].crop((0, 0, cut, line["sprite"].height)), (line["x"], line["y"])
            )
            _cursor(
                im, line["x"] + int(1 + line["prompt_w"] + res.type_x[typed]), res.baseline(i)
            )
        else:
            k = _ease((t - line["t0"]) / FADE)
            if k > 0:
                _composite(im, line["sprite"], (line["x"], line["y"]), k)

    closing = res.closing
    if t >= closing["t0"]:
        _composite(
            im,
            closing["sprite"],
            (closing["x"], closing["y"]),
            _ease((t - closing["t0"]) / FADE),
        )
        if (t - closing["t0"]) % 1.2 < 0.6:  # the SVG's 1.2s blink
            _cursor(im, closing["x"] + int(1 + res.advance), res.baseline(ROWS - 1))
    return im


def _endcard_frame(t: float) -> PilImage.Image:
    res = _resources()
    assert Image is not None
    im = Image.new("RGBA", (WIDTH, HEIGHT), _rgb(ENDCARD_BG))
    elements = (
        (res.endcard["logo"], 0.0),
        (res.endcard["chip"], CHIP_STAGGER),
        (res.endcard["link"], LINK_STAGGER),
        (res.endcard["tagline"], TAGLINE_STAGGER),
    )
    for (sprite, x, y), stagger in elements:
        k = _ease((t - stagger) / FADE)
        if k > 0:
            _composite(im, sprite, (x, y), k)
    return im


def render_frame(t: float) -> PilImage.Image:
    """The frame on screen at time ``t``: terminal, crossfade or end card."""
    assert Image is not None
    if t < TERMINAL_DURATION:
        frame = _terminal_frame(t)
    elif t < TERMINAL_DURATION + CROSSFADE:
        k = (t - TERMINAL_DURATION) / CROSSFADE
        terminal = _terminal_frame(TERMINAL_DURATION - 1e-9).convert("RGB")
        frame = Image.blend(terminal, _endcard_frame(t - TERMINAL_DURATION).convert("RGB"), k)
    else:
        frame = _endcard_frame(t - TERMINAL_DURATION)
    return frame.convert("RGB")


# ------------------------------------------------------------- encoding
def _ffmpeg_version() -> str:
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
    return out.stdout.splitlines()[0].split()[2]  # e.g. "n9.0.1"


def _encode_mp4(path: Path) -> None:
    """Pipe raw RGB frames straight into H.264 (yuv420p, web-friendly)."""
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        "-metadata",
        f"title=Aegis Zero v{demo.__version__} — offline demo",
        "-metadata",
        "comment=generated by scripts/make_video.py",
        str(path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(FRAMES):
        proc.stdin.write(render_frame(i / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {proc.returncode}")


def _encode_gif(source: Path, path: Path) -> None:
    """Two-pass palette GIF from the rendered MP4 (960x540 @ 15 fps)."""
    vf = (
        "fps=15,scale=960:-2:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:"
        "bayer_scale=4:diff_mode=rectangle"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            vf,
            "-loop",
            "0",
            str(path),
        ],
        check=True,
    )


# -------------------------------------------------------------- manifest
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest() -> dict[str, Any]:
    assert Image is not None
    files = {
        rel: {"bytes": (REPO / rel).stat().st_size, "sha256": _sha256(REPO / rel)}
        for rel in ASSETS
    }
    return {
        "generator": "scripts/make_video.py",
        "pinned_by": "tests/test_demo_video.py",
        "source": "examples/demo.py live transcript — same timeline as demo.cast/demo.svg",
        "frame": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "frames": FRAMES},
        "duration": {
            "terminal": TERMINAL_DURATION,
            "crossfade": CROSSFADE,
            "endcard": ENDCARD,
            "total": TOTAL,
        },
        "line_times": LINE_TIMES,
        "fonts": {"mono": font_name("mono"), "sans": font_name("sans")},
        "tools": {"ffmpeg": _ffmpeg_version(), "pillow": Image.__version__},
        "files": files,
    }


def _probe_mp4(manifest: dict[str, Any]) -> list[str]:
    """Cross-check the shipped MP4 against the manifest via ffprobe."""
    if shutil.which("ffprobe") is None:
        return []  # hash pinning still applied; just skip the container check
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_streams",
            "-of",
            "json",
            str(REPO / "docs" / "demo.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    stream = json.loads(out.stdout)["streams"][0]
    problems = []
    if (stream["width"], stream["height"]) != (WIDTH, HEIGHT):
        problems.append(
            f"mp4 is {stream['width']}x{stream['height']}, expected {WIDTH}x{HEIGHT}"
        )
    if abs(float(stream["duration"]) - TOTAL) > 0.2:
        problems.append(f"mp4 duration {stream['duration']:.2f}s, manifest says {TOTAL}s")
    frame = manifest["frame"]
    if round(float(stream["duration"]) * FPS) != frame["frames"]:
        problems.append(f"mp4 frame count disagrees with manifest ({frame['frames']})")
    return problems


def check() -> int:
    """Verify the shipped binaries match the committed manifest."""
    manifest = json.loads((REPO / MANIFEST).read_text(encoding="utf-8"))
    problems = []
    for rel, entry in manifest["files"].items():
        path = REPO / rel
        if not path.is_file():
            problems.append(f"missing: {rel}")
        elif path.stat().st_size != entry["bytes"] or _sha256(path) != entry["sha256"]:
            problems.append(f"drifted: {rel} — regenerate with: python scripts/make_video.py")
    problems.extend(_probe_mp4(manifest))
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print(f"video assets in sync ({', '.join(manifest['files'])})")
    return 0


# ------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Aegis Zero demo video assets.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the shipped assets against the manifest; exit 1 on drift",
    )
    parser.add_argument(
        "--probe", metavar="PNG", help="render a single frame to a PNG (Pillow only, no ffmpeg)"
    )
    parser.add_argument(
        "--at",
        type=float,
        default=POSTER_T,
        metavar="SECONDS",
        help="timestamp for --probe (default: the poster frame)",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check()
    if args.probe:
        out = Path(args.probe)
        render_frame(args.at).save(out)
        print(f"wrote {out} (frame at t={args.at:.2f}s)")
        return 0

    for tool in ("ffmpeg",):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} is required to render the video assets")
    if not (REPO / LOGO).is_file():
        raise RuntimeError(f"{LOGO} is missing — see the module docstring to rasterize it")

    mp4, gif, poster = (REPO / rel for rel in ASSETS)
    _encode_mp4(mp4)
    print(f"wrote {mp4.relative_to(REPO)} ({FRAMES} frames, {TOTAL}s)")
    _encode_gif(mp4, gif)
    print(f"wrote {gif.relative_to(REPO)}")
    render_frame(POSTER_T).save(poster)
    print(f"wrote {poster.relative_to(REPO)} (t={POSTER_T}s)")

    (REPO / MANIFEST).write_text(
        json.dumps(build_manifest(), indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {MANIFEST}")
    return check()  # a fresh render must verify against its own manifest


if __name__ == "__main__":
    raise SystemExit(main())
