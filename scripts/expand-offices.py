#!/usr/bin/env python3
"""Expand the pixel office by adding a duplicate office wing to the LEFT.

The new wing is placed to the left of the existing building.
Same structure as the original office area, with slight decoration changes
(different plants, different bookshelves, computers on desks).
Connected by an opening/glass wall.
"""
import json
import copy
from pathlib import Path

LAYOUT_FILE = Path(__file__).parent.parent / "dashboard/static/sprites/pixel-agents/default-layout.json"

with open(LAYOUT_FILE) as f:
    layout = json.load(f)

OLD_COLS = layout["cols"]
OLD_ROWS = layout["rows"]
old_tiles = layout["tiles"]
old_furn = layout["furniture"]
old_colors = layout.get("tileColors", [None] * len(old_tiles))
while len(old_colors) < len(old_tiles):
    old_colors.append(None)

# New wing: 12 columns prepended to the left
WING_WIDTH = 12
NEW_COLS = OLD_COLS + WING_WIDTH
NEW_ROWS = OLD_ROWS

# The office/building area in the original spans rows 10-20
WING_TOP = 10
WING_BOT = 20

def old_tile(r, c):
    if 0 <= r < OLD_ROWS and 0 <= c < OLD_COLS:
        return old_tiles[r * OLD_COLS + c]
    return 8

def old_color(r, c):
    if 0 <= r < OLD_ROWS and 0 <= c < OLD_COLS:
        idx = r * OLD_COLS + c
        return old_colors[idx] if idx < len(old_colors) else None
    return None

# Build new tile grid — prepend wing columns, then original
new_tiles = []
new_colors = []

for r in range(NEW_ROWS):
    for c in range(NEW_COLS):
        if c >= WING_WIDTH:
            # Original columns shifted right — keep exactly as-is
            orig_c = c - WING_WIDTH
            new_tiles.append(old_tile(r, orig_c))
            new_colors.append(old_color(r, orig_c))
        elif r < WING_TOP or r > WING_BOT:
            # Above or below wing area — void
            new_tiles.append(8)
            new_colors.append(None)
        else:
            # Inside the wing (rows 10-20, cols 0-11)
            if r == WING_TOP:
                # Top wall
                new_tiles.append(0)
                new_colors.append(None)
            elif r == WING_BOT:
                # Bottom wall
                new_tiles.append(0)
                new_colors.append(None)
            elif c == 0:
                # Left border wall
                new_tiles.append(0)
                new_colors.append(None)
            else:
                # Floor
                new_tiles.append(2)
                new_colors.append(None)

# Open the connecting wall between new wing and original building
# The original left wall was at col 0, now shifted to col WING_WIDTH (col 12)
# We need to open it where both sides have floor
for r in range(WING_TOP + 1, WING_BOT):
    wall_c = WING_WIDTH  # the original left wall, now at col 12
    idx = r * NEW_COLS + wall_c
    # Check if original had floor just inside (col 1 in original = col 13 in new)
    orig_inside = old_tile(r, 1)
    # Check if new wing has floor at col 11 (just left of the wall)
    wing_floor = new_tiles[r * NEW_COLS + (WING_WIDTH - 1)]
    if orig_inside in (1, 2, 6) and wing_floor == 2:
        new_tiles[idx] = 2  # open the wall

# Add wall pillars at the connection for glass-wall effect
for r in [WING_TOP + 1, WING_TOP + 5]:  # rows 11 and 15
    idx = r * NEW_COLS + WING_WIDTH
    new_tiles[idx] = 0  # wall pillar

# Add a horizontal wall divider in the new wing at row 15 (matching original structure)
for c in range(1, WING_WIDTH):
    idx = 15 * NEW_COLS + c
    if c in (5, 6):  # door opening
        new_tiles[idx] = 2
    else:
        new_tiles[idx] = 0

# Shift all original furniture positions by WING_WIDTH
new_furn = []
for item in old_furn:
    shifted = copy.deepcopy(item)
    shifted["col"] = item["col"] + WING_WIDTH
    new_furn.append(shifted)

# Add new furniture in the wing
def add(ftype, col, row, color=None):
    item = {"type": ftype, "col": col, "row": row}
    if color:
        item["color"] = color
    new_furn.append(item)

# === 4 DESK SETUPS WITH COMPUTERS ===

# Desk 1 (upper-left): row 12-13, cols 2-4
add("ASSET_NEW_106", 2, 12)            # desk
add("ASSET_49", 3, 13)                  # chair
add("ASSET_79", 3, 12)                  # monitor — same row as desk, 1 col right

# Desk 2 (upper-right): row 12-13, cols 7-9
add("ASSET_NEW_106", 7, 12)            # desk
add("ASSET_49", 8, 13)                  # chair
add("ASSET_108", 8, 12)                 # laptop — same row as desk, 1 col right

# Desk 3 (lower-left): row 16-17, cols 2-4
add("ASSET_NEW_106", 2, 16)            # desk
add("ASSET_49", 3, 17)                  # chair
add("ASSET_92", 3, 16)                  # full computer — same row as desk, 1 col right

# Desk 4 (lower-right): row 16-17, cols 7-9
add("ASSET_NEW_106", 7, 16)            # desk
add("ASSET_49", 8, 17)                  # chair
add("ASSET_79", 8, 16)                  # monitor — same row as desk, 1 col right

# === DECORATION — slightly different from original ===

# White bookshelves (original uses wooden ones)
add("ASSET_24", 4, 11)                  # full white bookshelf (upper area)
add("ASSET_29", 9, 11)                  # full white bookshelf 2 (upper area)
add("ASSET_23", 4, 15)                  # white bookshelf (lower area)
add("ASSET_28", 9, 15)                  # white bookshelf 2 (lower area)

# Different plants (original uses ASSET_31)
add("ASSET_140", 1, 13)                 # white plant 2
add("ASSET_142", 10, 13)                # plant 2 (different style)
add("ASSET_143", 1, 18)                 # plant 3
add("ASSET_133_0_0", 10, 18)            # white plant 1

# Books on some desks
add("ASSET_71", 4, 12)                  # blue book (desk 1)
add("ASSET_72", 9, 16)                  # red book (desk 4)

# Save
new_layout = {
    "version": 1,
    "cols": NEW_COLS,
    "rows": NEW_ROWS,
    "tiles": new_tiles,
    "tileColors": new_colors,
    "furniture": new_furn
}

with open(LAYOUT_FILE, 'w') as f:
    json.dump(new_layout, f, indent=2)

# Print
symbols = {0: '█', 1: '░', 2: '·', 6: '▓', 8: ' '}
print(f"New layout ({NEW_COLS}x{NEW_ROWS}):")
for r in range(NEW_ROWS):
    row_str = ""
    for c in range(NEW_COLS):
        t = new_tiles[r * NEW_COLS + c]
        row_str += symbols.get(t, '?')
    print(f"  {r:2d}: {row_str}")

print(f"\nFurniture: {len(old_furn)} → {len(new_furn)} items")
print("Saved to default-layout.json")
