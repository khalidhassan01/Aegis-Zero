# Zero — the Aegis Zero mark

> **This is Zero.** A shield behind rotating rings with a glowing 0 at its
> heart and gold it only earns when something is *verified*. Zero trusts
> nobody. Neither should your agent.

Zero is the face of Aegis Zero — the avatar you see on the GitHub org, the
favicon in your tab, the sticker on a laptop, and the end card of the demo
video. It is the **still form of the interactive hero logo**
([`docs/assets/aegis-zero-logo-interactive.svg`](../assets/aegis-zero-logo-interactive.svg)):
the same rings, the same shield, the same digit — caught mid-orbit instead
of spinning. Like a good security guard, Zero is friendly, wide awake, and
completely unimpressed by your excuses.

## Why this mark

One mark, three movements — every element is load-bearing:

| Element | Meaning |
|---|---|
| the shield | **the aegis** — protection; nothing executes unreviewed |
| the glowing ring at its heart | **the zero** — the digit 0: zero trust, zero swallowed failures |
| the dashed verdict ring | **the cycle** — plan, act, verify, repeat; it never stops turning |
| the gold counter-ring | **scrutiny** — the verifier running the other way, against the flow |
| the two sentinel dots | **the watch** — teal and gold, on opposite orbits: verification never sleeps |
| the measurement grid | **grounding** — the shield is glass over evidence, not a wall |
| the gold shoulder line | the v1 emblem's rim light, kept so the old logo still recognises its child |
| the gold tip light | **a verified answer** — gold is earned at the end, never assumed |

The mark is **text-free by design**: it must read at favicon size, in a round
crop, in any language, in one glance. If you see a ringed shield with a
glowing 0 — that's Zero, watching your tool calls.

## Personality (the marketing voice)

Zero is the project's ethos made legible:

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
| Aegis teal | `#00ffcc` | primary — rings, shield outline, the glowing zero |
| Gold | `#ffd700` | earned things only: counter-ring, sentinel, verified tip |
| Deep field | `#0a0a0a → #000000` | the avatar plate (round-crop safe) |
| Shield glass | `#00ffcc` @ 12% → 2% | the shield fill over the measurement grid |

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
| `zero-avatar.svg` | master avatar mark (still form of the interactive hero) |
| `zero-avatar-{512,256,128,64,32}.png` | GitHub/X/Discord avatars, favicons, stickers |
| `favicon.ico` | browser tab (16/32/48 packed) |
| `aegis-zero-lockup.svg/.png` | Zero beside the wordmark — slides, side-bars |
| `og-card.svg/.png` | 1200×630 Open Graph / X preview card |
| `endcard-lockup.svg/.png` | stacked lockup on pure black — the demo video end card |

## Usage rules

- **Clear space:** keep a margin of at least ¼ of the mark's diameter free
  around the avatar.
- **Minimum size:** 24px digital. Below that, use the favicon and accept
  that Zero becomes a glowing ring and a bright zero — which still works.
- **Round crops are safe by construction:** all art lives inside the
  circular plate; a test enforces it.
- **Don't:** recolour Zero (the teal is the brand), stretch it, drop the
  rings (a bare shield is just a shield), or set it on a busy background —
  give it its deep field or pure black.
- **Do:** let Zero be small, calm, and everywhere. Consistency is the moat.

## Rendering

```bash
python scripts/make_brand.py          # render all + refresh the manifest
python scripts/make_brand.py --check  # verify shipped binaries (no deps)
```

A `rsvg-convert` or Pillow upgrade that changes rasterisation will change
hashes — that is on purpose: regenerate and commit the renders with the
manifest, exactly like the demo assets.
