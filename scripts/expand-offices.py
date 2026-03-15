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

# ═══════════════════════════════════════════════════════════════════════════
# CEO OFFICE — large modern office to the RIGHT of meeting room
# Accessible ONLY through the meeting room door
# Carpet floor (tile 1), white modern desk, spacious + organized
# Size: 10 cols × 9 rows (cols 22-31, rows 1-9)
# ═══════════════════════════════════════════════════════════════════════════

CEO_LEFT = 22
CEO_RIGHT = 31
CEO_TOP = 1
CEO_BOT = 9

for r in range(CEO_TOP, CEO_BOT + 1):
    for c in range(CEO_LEFT, CEO_RIGHT + 1):
        idx = r * NEW_COLS + c
        if r == CEO_TOP or r == CEO_BOT or c == CEO_LEFT or c == CEO_RIGHT:
            new_tiles[idx] = 0   # wall
        else:
            new_tiles[idx] = 1   # carpet floor (lounge-style)

# Open doorway: meeting room right wall (col 21) + CEO left wall (col 22)
# Door at rows 4-5 (middle of the shared wall)
for r in [4, 5]:
    new_tiles[r * NEW_COLS + 21] = 2   # open meeting room right wall
    new_tiles[r * NEW_COLS + 22] = 1   # open CEO left wall (carpet)

# === CEO OFFICE FURNITURE (organized, spacious) ===
#
# Layout (interior cols 23-30, rows 2-8):
#   Row 2:  [plant]  .  .  .  .  . [bookshelf][bookshelf]
#   Row 3:  .  .  .  [desk desk desk]  .  [bookshelf][bookshelf]
#   Row 4:  door  .  .  [desk desk desk]  .  .  .
#   Row 5:  door  .  .  .  [chair] .  .  .  .
#   Row 6:  .  .  .  .  .  .  .  [bookshelf][bookshelf]
#   Row 7:  .  .  [guest]  .  .  [guest]  .  .
#   Row 8:  [plant]  .  .  .  .  .  .  [plant]

# --- DESK AREA (centered, rows 3-4) ---
# White modern desk (COUNTER_PLASTIC_SM = 3x2) — centered in room
add("ASSET_15", 26, 3)                # White desk (3 cols: 26-28, 2 rows: 3-4)
add("ASSET_79", 27, 3)                # Monitor ON desk (same row, 1 col right)

# Executive chair behind desk
add("ASSET_35", 27, 5)                # CHAIR_ROTATING_FRONT

# Coffee mug on desk
add("ASSET_51", 28, 3)                # COFFEE_MUG on desk right side

# --- GUEST SEATING (row 7, spaced out) ---
add("ASSET_38", 25, 7)                # CHAIR_CUSHIONED_BACK (guest left)
add("ASSET_38", 28, 7)                # CHAIR_CUSHIONED_BACK (guest right)

# --- BOOKSHELVES (right wall, white modern) ---
add("ASSET_24", 29, 2)                # FULL_WHITE_BOOKSHELF_1 (2x2) top-right
add("ASSET_29", 29, 4)                # FULL_WHITE_BOOKSHELF_2 (2x2) mid-right
add("ASSET_23", 29, 6)                # WHITE_BOOKSHELF_1 (2x2) bottom-right

# --- WALL DECORATIONS (on back wall, row 1) ---
add("ASSET_101", 26, 1)               # PAINTING_LANDSCAPE (2x2) centered above desk
add("ASSET_84", 24, 1)                # CLOCK_WALL_COLOR on left side of back wall

# --- PLANTS (corners for elegance) ---
add("ASSET_141", 23, 2)               # WHITE_PLANT_3 (top-left)
add("ASSET_133_0_0", 23, 8)           # WHITE_PLANT_1 (bottom-left)
add("ASSET_140", 30, 8)               # WHITE_PLANT_2 (bottom-right)

# --- ACCENT ITEMS ---
add("ASSET_106", 23, 5)               # TEXT_FRAME on left wall (motivational)

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
