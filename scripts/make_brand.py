"""Render the Aegis Zero brand kit from the committed SVG masters.

The mascot (**Zero**) and the lockups are authored as SVG in ``docs/brand/``;
this script pins their shipped raster renderings:

* ``zero-avatar-{512,256,128,64,32}.png`` — the avatar mark at every
  social/favicon size. 512 is rendered directly; smaller sizes are
  LANCZOS downscales of it, so every size tells the same story.
* ``favicon.ico``                       — 16/32/48 packed from the avatar.
* ``aegis-zero-lockup.png``             — Zero beside the wordmark.
* ``og-card.png``                       — 1200x630 Open Graph / X preview.
* ``endcard-lockup.png``                — stacked lockup on pure black, the
  plate ``scripts/make_video.py`` composites into the demo end card.
* ``brand.assets.json``                 — manifest (sha256 + bytes + size of
  every shipped binary); ``--check`` verifies the files against it and
  ``tests/test_brand.py`` fails the build on drift.

Generated output — never edit by hand. Regenerate with
``python scripts/make_brand.py`` (needs ``rsvg-convert`` + Pillow).
``--check`` needs neither. A renderer or Pillow upgrade that changes
rasterisation will change hashes: that is on purpose — regenerate and
commit the SVG renders and manifest together, exactly like the demo
assets (``scripts/make_video.py``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:  # Pillow is a *render-time* tool: the module stays importable without it
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]

REPO = Path(__file__).resolve().parents[1]
BRAND = REPO / "docs" / "brand"
RSVG = shutil.which("rsvg-convert")

MANIFEST = BRAND / "brand.assets.json"

AVATAR_SIZES = (512, 256, 128, 64, 32)
FAVICON_SIZES = (16, 32, 48)

# svg -> (png, render width, render height)
RENDERS: dict[str, tuple[str, int, int]] = {
    "zero-avatar.svg": ("zero-avatar-512.png", 512, 512),
    "aegis-zero-lockup.svg": ("aegis-zero-lockup.png", 780, 360),
    "og-card.svg": ("og-card.png", 1200, 630),
    "endcard-lockup.svg": ("endcard-lockup.png", 1200, 600),
}


def _digest(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    entry: dict[str, object] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if Image is not None:
        with Image.open(path) as im:
            entry["width"], entry["height"] = im.size
    return entry


def _render(svg: Path, png: Path, width: int, height: int) -> None:
    if RSVG is None:
        raise RuntimeError("rsvg-convert not found — install librsvg to render the brand kit")
    png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [RSVG, "-w", str(width), "-h", str(height), str(svg), "-o", str(png)],
        check=True,
    )


def _versions() -> dict[str, str]:
    out: dict[str, str] = {}
    if RSVG:
        v = subprocess.run([RSVG, "--version"], capture_output=True, text=True, check=True)
        out["rsvg-convert"] = v.stdout.strip()
    if Image is not None:
        from PIL import __version__ as pillow_version

        out["pillow"] = f"Pillow {pillow_version}"
    return out


def build() -> None:
    if Image is None:
        raise RuntimeError("Pillow is required to build the brand kit (downsizes + favicon)")

    for svg_name, (png_name, w, h) in RENDERS.items():
        _render(BRAND / svg_name, BRAND / png_name, w, h)
        print(f"rendered {png_name}")

    # every avatar size tells the same story: one render, faithful downscales
    with Image.open(BRAND / "zero-avatar-512.png") as master:
        for size in AVATAR_SIZES:
            if size == 512:
                continue
            with master.resize((size, size), Image.LANCZOS) as small:
                small.save(BRAND / f"zero-avatar-{size}.png")
            print(f"rendered zero-avatar-{size}.png")

    with Image.open(BRAND / "zero-avatar-512.png") as master:
        master.save(
            BRAND / "favicon.ico",
            sizes=[(s, s) for s in FAVICON_SIZES],
        )
    print("rendered favicon.ico")

    files: dict[str, dict[str, object]] = {}
    for name in (
        *(f"zero-avatar-{s}.png" for s in AVATAR_SIZES),
        "favicon.ico",
        "aegis-zero-lockup.png",
        "og-card.png",
        "endcard-lockup.png",
    ):
        files[f"docs/brand/{name}"] = _digest(BRAND / name)

    manifest = {
        "description": (
            "Aegis Zero brand kit — pinned raster renderings of the SVG masters "
            "in docs/brand/. Regenerate with scripts/make_brand.py; never edit "
            "the PNGs by hand."
        ),
        "tools": _versions(),
        "files": files,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(REPO)}")


def check() -> int:
    """Verify the shipped binaries against the manifest (no render deps)."""
    if not MANIFEST.is_file():
        print(f"fail: {MANIFEST.relative_to(REPO)} is missing", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad = 0
    for rel, pinned in manifest["files"].items():
        path = REPO / rel
        if not path.is_file():
            print(f"fail: {rel} is missing", file=sys.stderr)
            bad += 1
            continue
        actual = _digest(path)
        for key in ("bytes", "sha256"):
            if actual.get(key) != pinned.get(key):
                print(
                    f"fail: {rel} {key} drift ({actual.get(key)} != {pinned.get(key)})",
                    file=sys.stderr,
                )
                bad += 1
        if (
            "width" in pinned
            and "width" in actual
            and ((actual["width"], actual["height"]) != (pinned["width"], pinned["height"]))
        ):
            print(
                f"fail: {rel} dimensions drift {actual['width']}x{actual['height']}",
                file=sys.stderr,
            )
            bad += 1
    if bad:
        print(
            f"brand kit: {bad} mismatch(es) — regenerate with scripts/make_brand.py",
            file=sys.stderr,
        )
        return 1
    print(f"brand kit: {len(manifest['files'])} files match the manifest")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--check",
        action="store_true",
        help="verify shipped binaries against brand.assets.json (no deps)",
    )
    args = p.parse_args(argv)
    if args.check:
        return check()
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
