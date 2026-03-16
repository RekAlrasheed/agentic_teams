#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Workspace Cleanup — Auto-delete ephemeral files older than N days
#
# Deletes task done/, comms to-manager/, comms from-manager/ files older than
# the retention period. Does NOT touch workspace/outputs/ (permanent IP).
#
# Usage:
#   bash scripts/cleanup.sh              # delete files >7 days old
#   bash scripts/cleanup.sh --dry-run    # preview only
#   bash scripts/cleanup.sh --days 3     # custom retention period
# ──────────────────────────────────────────────────────────────────────────────

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

RETENTION_DAYS=7
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --days) RETENTION_DAYS="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

DIRS=(
    "$REPO_ROOT/workspace/tasks/done"
    "$REPO_ROOT/workspace/comms/to-manager"
    "$REPO_ROOT/workspace/comms/from-manager"
    "$REPO_ROOT/workspace/comms/from-manager/done"
)

TOTAL_DELETED=0
TOTAL_SIZE=0

echo "=== Workspace Cleanup ==="
echo "Retention: ${RETENTION_DAYS} days"
echo "Mode: $([ "$DRY_RUN" = true ] && echo "DRY RUN" || echo "LIVE")"
echo ""

for DIR in "${DIRS[@]}"; do
    [ -d "$DIR" ] || continue

    COUNT=0
    DIR_SIZE=0

    while IFS= read -r FILE; do
        [ -z "$FILE" ] && continue
        SIZE=$(stat -f%z "$FILE" 2>/dev/null || echo 0)
        DIR_SIZE=$((DIR_SIZE + SIZE))
        COUNT=$((COUNT + 1))

        if [ "$DRY_RUN" = true ]; then
            echo "  [DRY] would delete: $(basename "$FILE") (${SIZE}B)"
        else
            rm -f "$FILE"
        fi
    done < <(find "$DIR" -maxdepth 1 -type f ! -name '.gitkeep' -mtime +"$RETENTION_DAYS" 2>/dev/null)

    if [ "$COUNT" -gt 0 ]; then
        REL_DIR="${DIR#"$REPO_ROOT"/}"
        SIZE_KB=$((DIR_SIZE / 1024))
        echo "${REL_DIR}: ${COUNT} files (${SIZE_KB}KB)"
        TOTAL_DELETED=$((TOTAL_DELETED + COUNT))
        TOTAL_SIZE=$((TOTAL_SIZE + DIR_SIZE))
    fi
done

echo ""
TOTAL_KB=$((TOTAL_SIZE / 1024))
echo "=== Total: ${TOTAL_DELETED} files (${TOTAL_KB}KB) $([ "$DRY_RUN" = true ] && echo "would be deleted" || echo "deleted") ==="
