#!/usr/bin/env python3
"""Redesign the pixel office layout.

New layout:
  Row 0:      void border
  Rows 1-8:   8 offices (4 existing + 4 new empty) - arranged as 2 rows of 4
  Row 9:      corridor wall
  Rows 10-13: corridor (left) + kitchen (right)
  Row 14:     wall separator
  Rows 15-20: lounge (left) + meeting room (right)
"""
import json
from pathlib import Path

LAYOUT_FILE = Path(__file__).parent.parent / "dashboard/static/sprites/pixel-agents/default-layout.json"

# Load current layout
with open(LAYOUT_FILE) as f:
    layout = json.load(f)

old_tiles = layout["tiles"]
old_furn = layout["furniture"]

COLS, ROWS = 21, 21

# Tile types: 0=wall, 1=lounge-floor, 2=wood-floor, 6=kitchen-floor, 8=void

def make_grid():
    """Create a new 21x21 tile grid."""
    g = [8] * (COLS * ROWS)  # start all void

    def set_tile(r, c, val):
        if 0 <= r < ROWS and 0 <= c < COLS:
            g[r * COLS + c] = val

    def fill_rect(r1, c1, r2, c2, val):
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                set_tile(r, c, val)

    # === TOP SECTION: 8 OFFICES (rows 1-8) ===

    # Row 1: wall top for all offices
    fill_rect(1, 1, 1, 19, 0)

    # Office 1 (Navi): rows 2-4, cols 2-5
    fill_rect(2, 2, 4, 5, 2)
    fill_rect(2, 1, 4, 1, 0)  # left wall
    fill_rect(2, 6, 4, 6, 0)  # right wall/divider

    # Office 2 (Muse): rows 2-4, cols 7-10
    fill_rect(2, 7, 4, 10, 2)
    fill_rect(2, 11, 4, 11, 0)  # right wall/divider

    # Office 3 (empty): rows 2-4, cols 12-15
    fill_rect(2, 12, 4, 15, 2)
    fill_rect(2, 16, 4, 16, 0)  # right wall/divider

    # Office 4 (empty): rows 2-4, cols 17-19
    fill_rect(2, 17, 4, 19, 2)

    # Row 5: corridor between upper and lower offices
    fill_rect(5, 1, 5, 19, 2)
    fill_rect(5, 1, 5, 1, 0)  # left wall

    # Right wall for corridor
    fill_rect(5, 19, 5, 19, 2)  # floor, not wall, for walkway
    fill_rect(2, 19, 4, 19, 2)  # office 4 ends at 19, floor
    fill_rect(1, 19, 1, 19, 0)  # top wall continues

    # Office 5 (Arch): rows 6-8, cols 2-5
    fill_rect(6, 2, 8, 5, 2)
    fill_rect(6, 1, 8, 1, 0)  # left wall
    fill_rect(6, 6, 8, 6, 0)  # right wall/divider

    # Office 6 (Sage): rows 6-8, cols 7-10
    fill_rect(6, 7, 8, 10, 2)
    fill_rect(6, 11, 8, 11, 0)  # right wall/divider

    # Office 7 (empty): rows 6-8, cols 12-15
    fill_rect(6, 12, 8, 15, 2)
    fill_rect(6, 16, 8, 16, 0)  # right wall/divider

    # Office 8 (empty): rows 6-8, cols 17-19
    fill_rect(6, 17, 8, 19, 2)

    # Right wall for offices
    fill_rect(1, 20, 20, 20, 0)  # right border wall

    # === MIDDLE SECTION: CORRIDOR + KITCHEN (rows 9-13) ===

    # Row 9: wall separator
    fill_rect(9, 1, 9, 19, 0)
    # Door openings in the wall
    set_tile(9, 4, 2)   # door from office area to corridor
    set_tile(9, 5, 2)

    # Corridor (rows 10-13, cols 1-9)
    fill_rect(10, 1, 13, 1, 0)  # left wall
    fill_rect(10, 2, 13, 9, 2)  # corridor floor
    fill_rect(10, 10, 13, 10, 0)  # divider wall

    # Kitchen (rows 10-13, cols 11-19)
    fill_rect(10, 11, 13, 19, 6)  # kitchen floor (tan)

    # === BOTTOM SECTION: LOUNGE + MEETING ROOM (rows 14-20) ===

    # Row 14: wall separator
    fill_rect(14, 1, 14, 19, 0)
    # Door openings
    set_tile(14, 4, 2)  # door to lounge
    set_tile(14, 5, 2)
    set_tile(14, 14, 2)  # door to meeting room
    set_tile(14, 15, 2)

    # Lounge (rows 15-19, cols 1-9)
    fill_rect(15, 1, 19, 1, 0)  # left wall
    fill_rect(15, 2, 19, 9, 1)  # lounge floor (type 1)
    fill_rect(15, 10, 19, 10, 0)  # divider wall

    # Meeting room (rows 15-19, cols 11-19)
    fill_rect(15, 11, 19, 19, 2)  # meeting room floor

    # Row 20: bottom wall
    fill_rect(20, 1, 20, 19, 0)

    # Left and right borders
    fill_rect(0, 0, 20, 0, 8)   # col 0 = void
    fill_rect(0, 20, 20, 20, 0) # col 20 = wall

    # Top void
    fill_rect(0, 0, 0, 20, 8)

    return g


def make_furniture():
    """Create furniture list for the new layout."""
    furn = []

    # Helper to add furniture
    def add(asset_type, col, row, color=None):
        item = {"type": asset_type, "col": col, "row": row}
        if color:
            item["color"] = color
        furn.append(item)

    # === OFFICE DESKS (4 occupied + 4 empty) ===

    # Office 1 - Navi (rows 2-4, cols 2-5)
    add("ASSET_NEW_106", 2, 2)      # desk
    add("ASSET_49", 3, 3)            # chair

    # Office 2 - Muse (rows 2-4, cols 7-10)
    add("ASSET_NEW_106", 7, 2)      # desk
    add("ASSET_49", 8, 3)            # chair

    # Office 3 - Empty (rows 2-4, cols 12-15)
    add("ASSET_NEW_106", 12, 2)     # desk
    add("ASSET_49", 13, 3)           # chair

    # Office 4 - Empty (rows 2-4, cols 17-19)
    add("ASSET_NEW_106", 17, 2)     # desk
    add("ASSET_49", 18, 3)           # chair

    # Office 5 - Arch (rows 6-8, cols 2-5)
    add("ASSET_NEW_106", 2, 6)      # desk
    add("ASSET_49", 3, 7)            # chair

    # Office 6 - Sage (rows 6-8, cols 7-10)
    add("ASSET_NEW_106", 7, 6)      # desk
    add("ASSET_49", 8, 7)            # chair

    # Office 7 - Empty (rows 6-8, cols 12-15)
    add("ASSET_NEW_106", 12, 6)     # desk
    add("ASSET_49", 13, 7)           # chair

    # Office 8 - Empty (rows 6-8, cols 17-19)
    add("ASSET_NEW_106", 17, 6)     # desk
    add("ASSET_49", 18, 7)           # chair

    # Bookshelves in offices (decorative)
    add("ASSET_17", 4, 2)    # Office 1
    add("ASSET_17", 9, 2)    # Office 2
    add("ASSET_17", 14, 2)   # Office 3
    add("ASSET_17", 4, 6)    # Office 5
    add("ASSET_17", 9, 6)    # Office 6
    add("ASSET_17", 14, 6)   # Office 7

    # Plants in some offices
    add("ASSET_31", 5, 4)    # Office 1
    add("ASSET_31", 10, 4)   # Office 2
    add("ASSET_31", 5, 8)    # Office 5
    add("ASSET_31", 10, 8)   # Office 6

    # === KITCHEN (rows 10-13, cols 11-19) ===
    add("ASSET_55", 12, 10)    # coffee machine
    add("ASSET_151", 14, 10)   # microwave
    add("ASSET_NEW_106", 16, 10)  # counter
    add("ASSET_129", 18, 10)   # vending machine / fridge
    add("ASSET_31", 11, 13)    # plant

    # === LOUNGE (rows 15-19, cols 2-9) ===
    add("ASSET_44", 3, 16)     # couch left
    add("ASSET_44", 7, 16)     # couch right
    add("ASSET_NEW_106", 5, 17)  # coffee table
    add("ASSET_31", 2, 15)     # plant corner
    add("ASSET_31", 9, 15)     # plant corner
    add("ASSET_114", 5, 15)    # rug/carpet

    # === MEETING ROOM (rows 15-19, cols 11-19) ===
    add("ASSET_NEW_106", 13, 16)   # meeting table
    add("ASSET_NEW_106", 13, 17)   # meeting table (extension)
    add("ASSET_49", 12, 16)        # chair left
    add("ASSET_49", 12, 17)        # chair left
    add("ASSET_49", 16, 16)        # chair right
    add("ASSET_49", 16, 17)        # chair right
    add("ASSET_18", 11, 15)        # bookshelf (reference materials)
    add("ASSET_31", 19, 15)        # plant

    # === CORRIDOR DECORATION ===
    add("ASSET_31", 2, 10)     # plant in corridor
    add("ASSET_31", 9, 13)     # plant in corridor

    return furn


def make_tile_colors(tiles):
    """Create tile colors array — blue-tinted walls for meeting room."""
    colors = [None] * len(tiles)
    # Meeting room walls get a blue tint (Navaia branding)
    for r in range(14, 21):
        for c in range(10, 21):
            idx = r * COLS + c
            if tiles[idx] == 0:  # wall tiles in meeting area
                colors[idx] = {"h": 214, "s": 30, "b": -100, "c": -55}
    return colors


# Generate new layout
new_tiles = make_grid()
new_furniture = make_furniture()
new_tile_colors = make_tile_colors(new_tiles)

# Build new layout
new_layout = {
    "version": 1,
    "cols": COLS,
    "rows": ROWS,
    "tiles": new_tiles,
    "tileColors": new_tile_colors,
    "furniture": new_furniture
}

# Write output
with open(LAYOUT_FILE, 'w') as f:
    json.dump(new_layout, f, indent=2)

# Print the grid visually for verification
print("New layout grid:")
symbols = {0: '█', 1: '░', 2: '·', 6: '▓', 8: ' '}
for r in range(ROWS):
    row_str = ""
    for c in range(COLS):
        t = new_tiles[r * COLS + c]
        row_str += symbols.get(t, '?')
    print(f"  {r:2d}: {row_str}")

print(f"\nFurniture items: {len(new_furniture)}")
print("Layout saved to default-layout.json")
