# Zero — the Aegis Zero mascot

> **This is Zero.** A small round shield with a calm face, a dark zero where
> its heart should be, and a gold spark it only earns when something is
> *verified*. Zero trusts nobody. Neither should your agent.

Zero is the face of Aegis Zero — the avatar you see on the GitHub org, the
favicon in your tab, the sticker on a laptop, and the end card of the demo
video. Like a good security guard, Zero is friendly, wide awake, and
completely unimpressed by your excuses.

## Why this mark

One mark, three meanings — every element is load-bearing:

| Element | Meaning |
|---|---|
| the round shield body | **the aegis** — protection; nothing executes unreviewed |
| the body + dark ring | **the zero** — a shield that *is* the digit 0: zero trust, zero swallowed failures |
| the face | **grounded verification** — awake, calm, looking back at you; kawaii-sized eyes below the midline, because a guardian you can't look at is one you don't trust |
| the gold spark | **a verified answer** — gold is earned, never assumed |
| the three orbit dots | **heritage** — the v1 emblem's orbit rings, distilled to three points that survive favicon size |
| the gold tip light | the v1 emblem's tip dot, kept so the old logo still recognises its child |

The mark is **text-free by design**: it must read at favicon size, in a round
crop, in any language, in one glance. If you see a green circle with two eyes
and a small smile — that's Zero, watching your tool calls.

## Personality (the marketing voice)

Zero is the project's ethos made cute:

- **Calm, not casual.** Zero never panics; it returns typed errors.
- **Vigilant, not paranoid.** It watches everything and denies precisely.
- **Honest to a fault.** Zero never claims what it has not verified — the
  README's "proven / not proven" discipline is Zero's personality in prose.
- **Kind when it says no.** A denial is a saved run; a sanitisation is a
  second chance.

Taglines that ship with the mark:

- *Zero trusts nobody.*
- *Zero trust. Zero drama.*
- *Nothing executes unreviewed.*
- *Every answer earns its gold.*

## Palette & type

| Role | Hex | Notes |
|---|---|---|
| Aegis teal | `#00ffcc` | primary — outline, spark of the brand |
| Body gradient | `#33ffe3 → #00e0b8 → #00bd96` | the shield-zero body |
| Deep field | `#0d3f36 → #062420 → #020e0c` | the avatar plate (round-crop safe) |
| Ink | `#04241f` | eyes, smile, the zero-ring (`#053b33`) |
| Gold | `#ffd700` | earned things only: sparks, tip light, orbit |

Typography is unchanged from the v1 wordmark: **AEGIS** in Georgia 900 with
wide letterspacing, **Z E R O** in `'Courier New'` monospace, letterspaced —
a serif that has held a shield for two thousand years next to a terminal
that verifies one today.

## The kit

All rasters are generated from the SVG masters by `scripts/make_brand.py`
and pinned byte-for-byte in `brand.assets.json` (`tests/test_brand.py`
fails the build on drift). Never edit a PNG by hand — change the SVG,
regenerate, and commit the pair together.

| File | Use |
|---|---|
| `zero-avatar.svg` | master avatar mark |
| `zero-avatar-{512,256,128,64,32}.png` | GitHub/X/Discord avatars, favicons, stickers |
| `favicon.ico` | browser tab (16/32/48 packed) |
| `aegis-zero-lockup.svg/.png` | Zero beside the wordmark — slides, side-bars |
| `og-card.svg/.png` | 1200×630 Open Graph / X preview card |
| `endcard-lockup.svg/.png` | stacked lockup on pure black — the demo video end card |

## Usage rules

- **Clear space:** keep a margin of at least ¼ of the mark's diameter free
  around the avatar.
- **Minimum size:** 24px digital. Below that, use the favicon and accept
  that Zero becomes two dots and a smile — which still works.
- **Round crops are safe by construction:** all art lives inside the
  circular plate; a test enforces it.
- **Don't:** recolour Zero (the teal is the brand), stretch it, drop the
  face (a faceless shield is just a shield), or set it on a busy
  background — give it its deep field or pure black.
- **Do:** let Zero be small, calm, and everywhere. Consistency is the moat.

## Rendering

```bash
python scripts/make_brand.py          # render all + refresh the manifest
python scripts/make_brand.py --check  # verify shipped binaries (no deps)
```

A `rsvg-convert` or Pillow upgrade that changes rasterisation will change
hashes — that is on purpose: regenerate and commit the renders with the
manifest, exactly like the demo assets.
