#!/usr/bin/env python3
"""Generate logo.svg with JetBrains Mono ExtraBold glyphs converted to paths."""

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

FONT_PATH = "/usr/share/fonts/jetbrains-mono-fonts/JetBrainsMono-ExtraBold.otf"
LETTERS = "RELEASABLE"
# Which letters are ghost (0-indexed)
GHOST = {1, 3, 4, 6, 9}  # E, E, A, A, E
GHOST_OPACITY = 0.05
H_SCALE = 0.4
FONT_SIZE = 140
OUTPUT = "logo.svg"

font = TTFont(FONT_PATH)
glyf = font.getGlyphSet()
upm = font["head"].unitsPerEm
scale = FONT_SIZE / upm

# Extract paths and advance widths for each letter
glyphs = []
for ch in LETTERS:
    glyph_name = font.getBestCmap()[ord(ch)]
    pen = SVGPathPen(glyf)
    glyf[glyph_name].draw(pen)
    path_d = pen.getCommands()
    width = glyf[glyph_name].width
    glyphs.append((ch, path_d, width))

# Compute tight bounding box across all glyphs
global_ymin = float('inf')
global_ymax = float('-inf')
x_cursor = 0
for ch, path_d, adv in glyphs:
    glyph_name = font.getBestCmap()[ord(ch)]
    bp = BoundsPen(glyf)
    glyf[glyph_name].draw(bp)
    bounds = bp.bounds
    if bounds:
        _, ymin, _, ymax = bounds
        global_ymin = min(global_ymin, ymin)
        global_ymax = max(global_ymax, ymax)
    x_cursor += adv

total_advance = x_cursor
glyph_height = (global_ymax - global_ymin) * scale
svg_width = total_advance * scale * H_SCALE
svg_height = glyph_height
baseline_y = global_ymax * scale

parts = []
parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width:.1f} {svg_height:.1f}">')
parts.append('  <style>')
parts.append('    .letter { fill: #000000; }')
parts.append('    @media (prefers-color-scheme: dark) {')
parts.append('      .letter { fill: #ffffff; }')
parts.append('    }')
parts.append('  </style>')

x_cursor = 0
for i, (ch, path_d, adv) in enumerate(glyphs):
    opacity = f' opacity="{GHOST_OPACITY}"' if i in GHOST else ''
    tx = x_cursor * scale * H_SCALE
    parts.append(f'  <path class="letter" d="{path_d}" '
                 f'transform="translate({tx:.1f},{baseline_y:.1f}) scale({scale * H_SCALE:.6f},{-scale:.6f})"'
                 f'{opacity}/>')
    x_cursor += adv

parts.append('</svg>')

svg = '\n'.join(parts) + '\n'
with open(OUTPUT, 'w') as f:
    f.write(svg)

print(f"Wrote {OUTPUT} ({len(LETTERS)} glyphs, {svg_width:.0f}x{svg_height:.0f})")
