#!/usr/bin/env python3
"""Expand the pixel office by adding a duplicate office wing to the right.

Approach:
- Keep the ENTIRE original 21x21 layout untouched
- Add a new office room to the RIGHT, connected by a door/glass opening
- The new room has 4 empty desks (same furniture as existing agent desks)
- Only extends the building where the office area is (rows 10-20)
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

# Pad old_colors if shorter than tiles
while len(old_colors) < len(old_tiles):
    old_colors.append(None)

# New wing: 12 extra columns (wall + 10 floor + wall)
WING_WIDTH = 12
NEW_COLS = OLD_COLS + WING_WIDTH
NEW_ROWS = OLD_ROWS

# The office area in the original is rows 10-20
# We'll extend only those rows into the new wing
WING_TOP = 10   # row where the wing starts
WING_BOT = 20   # row where the wing ends

def old_tile(r, c):
    if 0 <= r < OLD_ROWS and 0 <= c < OLD_COLS:
        return old_tiles[r * OLD_COLS + c]
    return 8

def old_color(r, c):
    if 0 <= r < OLD_ROWS and 0 <= c < OLD_COLS:
        idx = r * OLD_COLS + c
        return old_colors[idx] if idx < len(old_colors) else None
    return None

# Build new tile grid
new_tiles = []
new_colors = []

for r in range(NEW_ROWS):
    for c in range(NEW_COLS):
        if c < OLD_COLS:
            # Original layout — keep exactly as-is
            new_tiles.append(old_tile(r, c))
            new_colors.append(old_color(r, c))
        elif r < WING_TOP or r > WING_BOT:
            # Above or below the wing area — void
            new_tiles.append(8)
            new_colors.append(None)
        else:
            # Inside the wing area (rows 10-20)
            wing_c = c - OLD_COLS  # 0..11 within the wing

            if r == WING_TOP:
                # Top wall of wing
                new_tiles.append(0)
                new_colors.append(None)
            elif r == WING_BOT:
                # Bottom wall of wing
                new_tiles.append(0)
                new_colors.append(None)
            elif wing_c == WING_WIDTH - 1:
                # Right wall of wing
                new_tiles.append(0)
                new_colors.append(None)
            else:
                # Floor inside the wing
                new_tiles.append(2)  # wood floor
                new_colors.append(None)

# Now open the connecting wall (col 20) between old and new wing
# Col 20 is the original right wall. Open it for rows 11-19 (the floor area)
for r in range(WING_TOP + 1, WING_BOT):
    idx_wall = r * NEW_COLS + (OLD_COLS - 1)  # col 20
    left = old_tile(r, OLD_COLS - 2)  # col 19
    if left in (1, 2, 6):  # if there's floor to the left
        new_tiles[idx_wall] = 2  # open the wall (make it floor)
    # Keep walls as walls where the original had non-floor

# Also need to open the first column of the new wing (col 21)
# It should be floor to connect to col 20
for r in range(WING_TOP + 1, WING_BOT):
    idx = r * NEW_COLS + OLD_COLS  # col 21
    if new_tiles[r * NEW_COLS + (OLD_COLS - 1)] == 2:  # if col 20 is now floor
        new_tiles[idx] = 2  # make col 21 floor too

# Add a glass/wall divider effect — keep wall at specific rows for visual separation
# Put wall pillars at the connection point to suggest a glass wall
for r in [WING_TOP + 1, WING_TOP + 5]:  # rows 11, 15 — pillar positions
    idx = r * NEW_COLS + (OLD_COLS - 1)
    new_tiles[idx] = 0  # wall pillar

# Duplicate office furniture into the new wing
# Original agent desks are at approximately:
#   Navi:  desk at (2,14), chair at (3,16) — col 2-5, rows 14-16
#   Muse:  desk at (7,14), chair at (8,16) — col 7-10, rows 14-16
#   Arch:  desk at (2,18), chair at (3,20) — col 2-5, rows 18-20
#   Sage:  desk at (7,18), chair at (8,20) — col 7-10, rows 18-20
#
# In the new wing, the floor area is cols 21-31, rows 11-19
# Let's place 4 desks similarly:
#   New desk 1: cols 22-25, rows 12-14
#   New desk 2: cols 27-30, rows 12-14
#   New desk 3: cols 22-25, rows 16-18
#   New desk 4: cols 27-30, rows 16-18

new_furn = copy.deepcopy(old_furn)

# Find what furniture types are used for the existing desks
# Look at furniture near the agent positions
desk_type = None
chair_type = None
for item in old_furn:
    if item["type"] in ("ASSET_NEW_106",):
        desk_type = item["type"]
    if item["type"] in ("ASSET_49",):
        chair_type = item["type"]
    # Also check for specific desk/chair patterns
    if "color" not in item:
        if item.get("type", "").startswith("ASSET"):
            pass

# If we couldn't find them, use common defaults
if not desk_type:
    desk_type = "ASSET_NEW_106"
if not chair_type:
    chair_type = "ASSET_49"

print(f"Desk type: {desk_type}, Chair type: {chair_type}")

# Add 4 desk+chair pairs in the new wing
# Row arrangement matches the original office layout
wing_start_col = OLD_COLS + 1  # col 22

def add_furn(ftype, col, row, color=None):
    item = {"type": ftype, "col": col, "row": row}
    if color:
        item["color"] = color
    new_furn.append(item)

# Desk pair 1 (top-left of new wing)
add_furn(desk_type, wing_start_col, 12)
add_furn(chair_type, wing_start_col + 1, 13)

# Desk pair 2 (top-right of new wing)
add_furn(desk_type, wing_start_col + 5, 12)
add_furn(chair_type, wing_start_col + 6, 13)

# Desk pair 3 (bottom-left of new wing)
add_furn(desk_type, wing_start_col, 16)
add_furn(chair_type, wing_start_col + 1, 17)

# Desk pair 4 (bottom-right of new wing)
add_furn(desk_type, wing_start_col + 5, 16)
add_furn(chair_type, wing_start_col + 6, 17)

# Add some decorative items
bookshelf_type = "ASSET_17"  # bookshelf (used in original offices)
plant_type = "ASSET_31"       # plant

# Bookshelves against the wall
add_furn(bookshelf_type, wing_start_col + 3, 11)
add_furn(bookshelf_type, wing_start_col + 8, 11)

# Plants
add_furn(plant_type, wing_start_col + 9, 12)
add_furn(plant_type, wing_start_col + 9, 17)

# Wall divider between upper and lower desk pairs (row 15)
for c_offset in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
    r = 15
    c = wing_start_col + c_offset
    idx = r * NEW_COLS + c
    # Make a partial wall with door openings
    if c_offset in (3, 4):
        new_tiles[idx] = 2  # door opening
    else:
        new_tiles[idx] = 0  # wall

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
print(f"\nNew layout ({NEW_COLS}x{NEW_ROWS}):")
for r in range(NEW_ROWS):
    row_str = ""
    for c in range(NEW_COLS):
        t = new_tiles[r * NEW_COLS + c]
        row_str += symbols.get(t, '?')
    print(f"  {r:2d}: {row_str}")

print(f"\nFurniture: {len(old_furn)} → {len(new_furn)} items")
print("Saved to default-layout.json")
