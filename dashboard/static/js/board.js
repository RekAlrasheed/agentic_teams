/* ═══════════════════════════════════════════════════════
   NAVAIA CREW HQ — Trello Board View
   ═══════════════════════════════════════════════════════ */

let boardData = null;

async function loadBoard() {
    try {
        boardData = await CrewHQ.getTrello();
        renderBoard();
    } catch (err) {
        console.error('Board load error:', err);
    }
}

function renderBoard() {
    const el = document.getElementById('kanban-board');
    const statusEl = document.getElementById('board-status');

    if (!boardData || !boardData.enabled) {
        el.innerHTML = `
            <div class="empty-state" style="width: 100%;">
                <span class="pixel-icon">&#9632;</span>
                <div class="message">TRELLO NOT CONFIGURED</div>
                <p style="margin-top: 12px; color: var(--text-dim);">
                    Set TRELLO_KEY, TRELLO_TOKEN, and TRELLO_BOARD_ID in your .env file
                </p>
            </div>`;
        statusEl.textContent = 'Not configured';
        return;
    }

    if (boardData.error) {
        el.innerHTML = `<div class="empty-state" style="width: 100%;"><div class="message">${boardData.error}</div></div>`;
        statusEl.textContent = 'Error';
        return;
    }

    const totalCards = boardData.lists.reduce((sum, l) => sum + l.cards.length, 0);
    statusEl.textContent = `${totalCards} cards | Auto-refresh 10s`;

    el.innerHTML = boardData.lists.map(list => `
        <div class="kanban-column">
            <div class="kanban-header">
                ${list.name}
                <span class="kanban-count">${list.cards.length}</span>
            </div>
            <div class="kanban-cards">
                ${list.cards.length === 0 ? '<div style="color: var(--text-dim); font-size: 14px; text-align: center; padding: 10px;">Empty</div>' : ''}
                ${list.cards.map(card => `
                    <div class="kanban-card" onclick="showCardDetail('${escapeHtml(card.name)}', '${escapeHtml(card.desc)}')">
                        <div class="card-title">${escapeHtml(card.name)}</div>
                        ${card.desc ? `<div class="card-desc">${escapeHtml(card.desc)}</div>` : ''}
                        <div class="card-labels">
                            ${card.labels.map(l => `
                                <span class="card-label" style="background: ${l.color}">${l.name}</span>
                            `).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

function showCardDetail(name, desc) {
    showModal(`
        <div class="modal-title">${name}</div>
        <div style="font-size: 16px; color: var(--text-dim); line-height: 1.6; white-space: pre-wrap;">${desc || 'No description.'}</div>
        <div class="modal-actions">
            <button class="pixel-btn secondary" onclick="closeModal()">CLOSE</button>
        </div>
    `);
}

// Auto-refresh
setInterval(loadBoard, 10000);

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    loadBoard();
    CrewHQ.onUpdate(() => {
        document.getElementById('conn-dot').className = 'status-dot online';
    });
});
