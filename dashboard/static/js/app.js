/* ═══════════════════════════════════════════════════════
   NAVAIA CREW HQ — Shared App Logic
   ═══════════════════════════════════════════════════════ */

const CrewHQ = {
    state: null,
    listeners: [],
    eventSource: null,

    // ── SSE Connection ──────────────────────────────────
    connect() {
        if (this.eventSource) this.eventSource.close();
        this.eventSource = new EventSource('/api/events');

        this.eventSource.addEventListener('state', (e) => {
            try {
                this.state = JSON.parse(e.data);
                this.notify();
            } catch (err) {
                console.error('SSE parse error:', err);
            }
        });

        this.eventSource.onerror = () => {
            console.warn('SSE connection lost, reconnecting...');
            setTimeout(() => this.connect(), 3000);
        };

        // Also fetch initial state
        this.fetchState();
    },

    async fetchState() {
        try {
            const r = await fetch('/api/state');
            this.state = await r.json();
            this.notify();
        } catch (err) {
            console.error('Fetch state error:', err);
        }
    },

    onUpdate(fn) {
        this.listeners.push(fn);
        if (this.state) fn(this.state);
    },

    notify() {
        this.listeners.forEach(fn => {
            try { fn(this.state); } catch (e) { console.error(e); }
        });
    },

    // ── API Helpers ─────────────────────────────────────
    async createTask(agent, title, description) {
        const r = await fetch('/api/task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent, title, description }),
        });
        const data = await r.json();
        if (data.ok) {
            showToast(`Task assigned!`);
            this.fetchState();
        } else {
            showToast(data.error || 'Failed', true);
        }
        return data;
    },

    async sendChat(message) {
        const r = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });
        return await r.json();
    },

    async getChatHistory() {
        const r = await fetch('/api/chat/history');
        return await r.json();
    },

    async getTrello() {
        const r = await fetch('/api/trello');
        return await r.json();
    },

    async getOutputs() {
        const r = await fetch('/api/outputs');
        return await r.json();
    },

    async getOutputContent(path) {
        const r = await fetch(`/api/output/${encodeURIComponent(path)}`);
        return await r.json();
    },

    async getAgents() {
        const r = await fetch('/api/agents');
        return await r.json();
    },

    async createAgent(data) {
        const r = await fetch('/api/agents', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        return await r.json();
    },

    async deleteAgent(id) {
        const r = await fetch(`/api/agents/${id}`, { method: 'DELETE' });
        return await r.json();
    },
};

// ── Navigation ──────────────────────────────────────────
function initNav() {
    const path = window.location.pathname;
    document.querySelectorAll('.nav-links a').forEach(a => {
        if (a.getAttribute('href') === path) {
            a.classList.add('active');
        }
    });
}

// ── Toast Notifications ─────────────────────────────────
function showToast(msg, isError = false) {
    const toast = document.createElement('div');
    toast.className = `toast${isError ? ' error' : ''}`;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// ── Helpers ─────────────────────────────────────────────
function timeAgo(isoString) {
    const now = new Date();
    const then = new Date(isoString);
    const secs = Math.floor((now - then) / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

function shortTime(isoString) {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function agentColor(agentId) {
    const colors = {
        pm: '#4a9eff', navi: '#4a9eff',
        creative: '#ff8c42', muse: '#ff8c42',
        technical: '#a855f7', arch: '#a855f7',
        admin: '#22c55e', sage: '#22c55e',
    };
    return colors[agentId?.toLowerCase()] || '#666';
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Modal ───────────────────────────────────────────────
function showModal(contentHtml) {
    let overlay = document.querySelector('.modal-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        document.body.appendChild(overlay);
    }
    overlay.innerHTML = `<div class="modal">${contentHtml}</div>`;
    overlay.classList.add('show');
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });
}

function closeModal() {
    const overlay = document.querySelector('.modal-overlay');
    if (overlay) overlay.classList.remove('show');
}

// ── Task Assignment Modal ───────────────────────────────
function showTaskModal(agentId) {
    const agents = CrewHQ.state?.agents || [];
    const options = agents.map(a =>
        `<option value="${a.id}" ${a.id === agentId ? 'selected' : ''}>${a.name} (${a.role})</option>`
    ).join('');

    showModal(`
        <div class="modal-title">ASSIGN TASK</div>
        <form class="pixel-form" onsubmit="submitTask(event)">
            <label>AGENT</label>
            <select class="pixel-select" id="modal-agent">${options}</select>
            <label>TASK TITLE</label>
            <input class="pixel-input" id="modal-title" placeholder="What needs to be done?" required>
            <label>DESCRIPTION</label>
            <textarea class="pixel-textarea" id="modal-desc" placeholder="Details, requirements, context..." rows="4"></textarea>
            <div class="modal-actions">
                <button type="button" class="pixel-btn secondary" onclick="closeModal()">CANCEL</button>
                <button type="submit" class="pixel-btn">ASSIGN</button>
            </div>
        </form>
    `);
    document.getElementById('modal-title').focus();
}

async function submitTask(e) {
    e.preventDefault();
    const agent = document.getElementById('modal-agent').value;
    const title = document.getElementById('modal-title').value;
    const desc = document.getElementById('modal-desc').value;
    await CrewHQ.createTask(agent, title, desc);
    closeModal();
}

// ── Init ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initNav();
    CrewHQ.connect();
});
