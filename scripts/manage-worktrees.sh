#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Manage Agent Worktrees — Setup, status, cleanup, and reset
#
# Usage:
#   bash scripts/manage-worktrees.sh status     # Show all worktree statuses
#   bash scripts/manage-worktrees.sh setup       # Create worktrees for all agents
#   bash scripts/manage-worktrees.sh cleanup     # Remove all agent worktrees
#   bash scripts/manage-worktrees.sh reset       # Reset all worktrees to main
# ──────────────────────────────────────────────────────────────────────────────

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

WORKTREE_BASE="${REPO_ROOT}/.worktrees"
AGENTS=("pm" "creative" "technical" "admin")

# Add any additional agents from the agents/ directory
for agent_dir in agents/*/; do
    agent_name=$(basename "$agent_dir")
    # Skip if already in the list
    if [[ ! " ${AGENTS[*]} " =~ " ${agent_name} " ]]; then
        AGENTS+=("$agent_name")
    fi
done

cmd="${1:-status}"

case "$cmd" in
    status)
        echo "Agent Worktree Status"
        echo "─────────────────────────────────────"
        git worktree list 2>/dev/null
        echo ""
        for agent in "${AGENTS[@]}"; do
            wt_dir="${WORKTREE_BASE}/${agent}"
            branch="agent/${agent}-workspace"
            if [ -d "$wt_dir" ] && [ -f "$wt_dir/.git" ]; then
                # Check branch
                cur_branch=$(cd "$wt_dir" && git branch --show-current 2>/dev/null || echo "???")
                # Check for uncommitted changes
                changes=$(cd "$wt_dir" && git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
                # Check symlinks
                ws_ok="NO"
                [ -L "$wt_dir/workspace" ] && ws_ok="OK"
                echo "  $agent: ACTIVE (branch: $cur_branch, changes: $changes, workspace symlink: $ws_ok)"
            else
                echo "  $agent: NOT CREATED"
            fi
        done
        ;;

    setup)
        echo "Setting up worktrees for all agents..."
        mkdir -p "$WORKTREE_BASE"
        for agent in "${AGENTS[@]}"; do
            wt_dir="${WORKTREE_BASE}/${agent}"
            branch="agent/${agent}-workspace"

            if [ -d "$wt_dir" ] && [ -f "$wt_dir/.git" ]; then
                echo "  $agent: already exists, skipping"
                continue
            fi

            # Create branch if needed
            if ! git rev-parse --verify "$branch" >/dev/null 2>&1; then
                git branch "$branch" main 2>/dev/null
                echo "  $agent: created branch $branch"
            fi

            git worktree prune 2>/dev/null || true
            if git worktree add "$wt_dir" "$branch" 2>/dev/null; then
                # Create symlinks
                rm -rf "$wt_dir/workspace"
                ln -sf "$REPO_ROOT/workspace" "$wt_dir/workspace"
                rm -f "$wt_dir/.env"
                ln -sf "$REPO_ROOT/.env" "$wt_dir/.env"
                [ -d "$REPO_ROOT/knowledge" ] && { rm -rf "$wt_dir/knowledge"; ln -sf "$REPO_ROOT/knowledge" "$wt_dir/knowledge"; }
                [ -d "$REPO_ROOT/node_modules" ] && { rm -rf "$wt_dir/node_modules"; ln -sf "$REPO_ROOT/node_modules" "$wt_dir/node_modules"; }
                echo "  $agent: created at $wt_dir (branch: $branch)"
            else
                echo "  $agent: FAILED to create worktree"
            fi
        done
        echo "Done."
        ;;

    cleanup)
        echo "Removing all agent worktrees..."
        for agent in "${AGENTS[@]}"; do
            wt_dir="${WORKTREE_BASE}/${agent}"
            if [ -d "$wt_dir" ]; then
                git worktree remove "$wt_dir" --force 2>/dev/null || rm -rf "$wt_dir"
                echo "  $agent: removed"
            else
                echo "  $agent: not found, skipping"
            fi
        done
        git worktree prune 2>/dev/null || true
        rmdir "$WORKTREE_BASE" 2>/dev/null || true
        echo "Done."
        ;;

    reset)
        echo "Resetting all agent worktrees to main..."
        for agent in "${AGENTS[@]}"; do
            wt_dir="${WORKTREE_BASE}/${agent}"
            if [ -d "$wt_dir" ] && [ -f "$wt_dir/.git" ]; then
                cd "$wt_dir"
                git checkout -- . 2>/dev/null || true
                git clean -fd 2>/dev/null || true
                git reset --hard main 2>/dev/null || true
                cd "$REPO_ROOT"
                echo "  $agent: reset to main"
            else
                echo "  $agent: not found, skipping"
            fi
        done
        echo "Done."
        ;;

    *)
        echo "Usage: bash scripts/manage-worktrees.sh <status|setup|cleanup|reset>"
        exit 1
        ;;
esac
