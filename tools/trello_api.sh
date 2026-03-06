#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Navaia AI Workforce — Trello API Helpers
#
# Source this file to use Trello functions:
#   source tools/trello_api.sh
#
# Requires .env with: TRELLO_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Load .env if not already loaded
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

# Validate required env vars
_trello_check_env() {
    if [ -z "${TRELLO_KEY:-}" ] || [ -z "${TRELLO_TOKEN:-}" ] || [ -z "${TRELLO_BOARD_ID:-}" ]; then
        echo "ERROR: TRELLO_KEY, TRELLO_TOKEN, and TRELLO_BOARD_ID must be set in .env" >&2
        return 1
    fi
}

# Base URL and auth params
_TRELLO_BASE="https://api.trello.com/1"
_trello_auth() {
    echo "key=${TRELLO_KEY}&token=${TRELLO_TOKEN}"
}

# ── Board Setup ──────────────────────────────────────────────────────────────

trello_setup_board() {
    # Create all lists and labels on the board (run once during setup)
    _trello_check_env || return 1

    echo "Setting up Trello board..."

    # Create lists (in reverse order so they appear correctly)
    local lists=("Rejected" "Blocked" "Done" "Review" "In Progress" "To Do" "Planning" "Inbox")
    for list_name in "${lists[@]}"; do
        curl -s -X POST "${_TRELLO_BASE}/boards/${TRELLO_BOARD_ID}/lists?$(_trello_auth)&name=${list_name}" \
            -o /dev/null
        echo "  Created list: ${list_name}"
    done

    # Create labels
    declare -A labels=(
        ["PM"]="blue"
        ["Creative"]="orange"
        ["Technical"]="purple"
        ["Admin"]="green"
    )
    for label_name in "${!labels[@]}"; do
        local color="${labels[$label_name]}"
        curl -s -X POST "${_TRELLO_BASE}/boards/${TRELLO_BOARD_ID}/labels?$(_trello_auth)&name=${label_name}&color=${color}" \
            -o /dev/null
        echo "  Created label: ${label_name} (${color})"
    done

    echo "Trello board setup complete."
}

# ── List Operations ──────────────────────────────────────────────────────────

trello_get_list_id() {
    # Get a list's ID by name
    # Usage: trello_get_list_id "To Do"
    _trello_check_env || return 1
    local list_name="$1"

    curl -s "${_TRELLO_BASE}/boards/${TRELLO_BOARD_ID}/lists?$(_trello_auth)" \
        | python3 -c "
import sys, json
lists = json.load(sys.stdin)
for l in lists:
    if l['name'] == '${list_name}':
        print(l['id'])
        sys.exit(0)
print('NOT_FOUND', file=sys.stderr)
sys.exit(1)
"
}

# ── Label Operations ─────────────────────────────────────────────────────────

trello_get_label_id() {
    # Get a label's ID by name
    # Usage: trello_get_label_id "Creative"
    _trello_check_env || return 1
    local label_name="$1"

    curl -s "${_TRELLO_BASE}/boards/${TRELLO_BOARD_ID}/labels?$(_trello_auth)" \
        | python3 -c "
import sys, json
labels = json.load(sys.stdin)
for l in labels:
    if l['name'] == '${label_name}':
        print(l['id'])
        sys.exit(0)
print('NOT_FOUND', file=sys.stderr)
sys.exit(1)
"
}

# ── Card Operations ──────────────────────────────────────────────────────────

trello_create_card() {
    # Create a card in a specific list with optional label
    # Usage: trello_create_card "To Do" "Card Title" "Card Description" "Creative"
    # Returns: card ID
    _trello_check_env || return 1
    local list_name="$1"
    local card_title="$2"
    local card_desc="${3:-}"
    local label_name="${4:-}"

    local list_id
    list_id=$(trello_get_list_id "$list_name")

    local url="${_TRELLO_BASE}/cards?$(_trello_auth)&idList=${list_id}"
    url+="&name=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${card_title}'))")"

    if [ -n "$card_desc" ]; then
        url+="&desc=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${card_desc}'))")"
    fi

    if [ -n "$label_name" ]; then
        local label_id
        label_id=$(trello_get_label_id "$label_name")
        url+="&idLabels=${label_id}"
    fi

    local response
    response=$(curl -s -X POST "$url")
    echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])"
}

trello_move_card() {
    # Move a card to a different list
    # Usage: trello_move_card "CARD_ID" "In Progress"
    _trello_check_env || return 1
    local card_id="$1"
    local list_name="$2"

    local list_id
    list_id=$(trello_get_list_id "$list_name")

    curl -s -X PUT "${_TRELLO_BASE}/cards/${card_id}?$(_trello_auth)&idList=${list_id}" \
        -o /dev/null
    echo "Moved card ${card_id} to ${list_name}"
}

trello_comment() {
    # Add a comment to a card
    # Usage: trello_comment "CARD_ID" "This is my comment"
    _trello_check_env || return 1
    local card_id="$1"
    local comment="$2"

    local encoded_comment
    encoded_comment=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${comment}'))")

    curl -s -X POST "${_TRELLO_BASE}/cards/${card_id}/actions/comments?$(_trello_auth)&text=${encoded_comment}" \
        -o /dev/null
    echo "Comment added to card ${card_id}"
}

trello_add_checklist() {
    # Add a checklist with items to a card
    # Usage: trello_add_checklist "CARD_ID" "Subtasks" "item1" "item2" "item3"
    _trello_check_env || return 1
    local card_id="$1"
    local checklist_name="$2"
    shift 2
    local items=("$@")

    # Create checklist
    local checklist_response
    checklist_response=$(curl -s -X POST "${_TRELLO_BASE}/cards/${card_id}/checklists?$(_trello_auth)&name=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${checklist_name}'))")")

    local checklist_id
    checklist_id=$(echo "$checklist_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")

    # Add items
    for item in "${items[@]}"; do
        local encoded_item
        encoded_item=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${item}'))")
        curl -s -X POST "${_TRELLO_BASE}/checklists/${checklist_id}/checkItems?$(_trello_auth)&name=${encoded_item}" \
            -o /dev/null
    done

    echo "Checklist '${checklist_name}' added to card ${card_id} with ${#items[@]} items"
}

trello_list_cards() {
    # List all cards in a specific list
    # Usage: trello_list_cards "In Progress"
    _trello_check_env || return 1
    local list_name="$1"

    local list_id
    list_id=$(trello_get_list_id "$list_name")

    curl -s "${_TRELLO_BASE}/lists/${list_id}/cards?$(_trello_auth)" \
        | python3 -c "
import sys, json
cards = json.load(sys.stdin)
if not cards:
    print('No cards in this list.')
else:
    for c in cards:
        labels = ', '.join([l['name'] for l in c.get('labels', [])])
        print(f\"  [{c['id'][:8]}] {c['name']}\" + (f' ({labels})' if labels else ''))
"
}

trello_status() {
    # Print a summary of card counts per list
    _trello_check_env || return 1

    echo "📊 Trello Board Status"
    echo "─────────────────────"

    curl -s "${_TRELLO_BASE}/boards/${TRELLO_BOARD_ID}/lists?$(_trello_auth)&cards=all" \
        | python3 -c "
import sys, json
lists = json.load(sys.stdin)
for l in lists:
    cards = l.get('cards', [])
    count = len(cards)
    icon = {'Inbox': '📥', 'Planning': '📋', 'To Do': '📝', 'In Progress': '🔄', 'Review': '🔍', 'Done': '✅', 'Blocked': '🚫', 'Rejected': '❌'}.get(l['name'], '📌')
    print(f\"  {icon} {l['name']}: {count}\")
"
}
