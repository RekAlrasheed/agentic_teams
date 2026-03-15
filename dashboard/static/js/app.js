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

    // ── Agent Detail API ─────────────────────────────
    async getAgentStatus(agentId) {
        const r = await fetch(`/api/agent/${agentId}/status`);
        return await r.json();
    },

    async getAgentTasks(agentId) {
        const r = await fetch(`/api/agent/${agentId}/tasks`);
        return await r.json();
    },

    async getAgentTaskContent(agentId, filename) {
        const r = await fetch(`/api/agent/${agentId}/task/${encodeURIComponent(filename)}`);
        return await r.json();
    },

    async cancelAgentTask(agentId, filename) {
        const r = await fetch(`/api/agent/${agentId}/task/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        return await r.json();
    },

    async reorderAgentTasks(agentId, filenames) {
        const r = await fetch(`/api/agent/${agentId}/task/reorder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filenames }),
        });
        return await r.json();
    },

    async getAgentOutputs(agentId) {
        const r = await fetch(`/api/agent/${agentId}/outputs`);
        return await r.json();
    },

    async getAgentOutputContent(agentId, filename) {
        const r = await fetch(`/api/agent/${agentId}/output/${encodeURIComponent(filename)}`);
        return await r.json();
    },

    async sendAgentChat(agentId, message) {
        const r = await fetch(`/api/agent/${agentId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });
        return await r.json();
    },

    async getAgentChatHistory(agentId) {
        const r = await fetch(`/api/agent/${agentId}/chat/history`);
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
    return div.innerHTML.replace(/\n/g, '<br>');
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

// ── Agent Detail Panel ─────────────────────────────────

const AgentDetail = {
    currentAgent: null,
    currentTab: 'status',
    chatMessages: [],
    refreshInterval: null,

    async open(agentId) {
        this.currentAgent = agentId;
        this.currentTab = 'status';
        const panel = document.getElementById('agent-detail-panel');
        if (!panel) return;
        panel.style.display = 'block';
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        await this.refresh();
        // Auto-refresh every 5s while open
        clearInterval(this.refreshInterval);
        this.refreshInterval = setInterval(() => {
            if (this.currentAgent && this.currentTab === 'status') this.refreshStatus();
        }, 5000);
    },

    close() {
        this.currentAgent = null;
        clearInterval(this.refreshInterval);
        const panel = document.getElementById('agent-detail-panel');
        if (panel) panel.style.display = 'none';
    },

    switchTab(tab) {
        this.currentTab = tab;
        document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
        const activeTab = document.querySelector(`.detail-tab[data-tab="${tab}"]`);
        if (activeTab) activeTab.classList.add('active');
        this.refresh();
    },

    async refresh() {
        const tab = this.currentTab;
        if (tab === 'status') await this.refreshStatus();
        else if (tab === 'tasks') await this.refreshTasks();
        else if (tab === 'outputs') await this.refreshOutputs();
        else if (tab === 'chat') await this.refreshChat();
    },

    async refreshStatus() {
        if (!this.currentAgent) return;
        const status = await CrewHQ.getAgentStatus(this.currentAgent);
        if (status.error) return;

        const header = document.getElementById('detail-panel-header');
        if (header) {
            header.innerHTML = `<span style="color:${status.color}">${status.name}</span> — ${status.role}
                <button class="pixel-btn small secondary" onclick="AgentDetail.close()" style="margin-left:auto;">CLOSE ✕</button>`;
        }

        const content = document.getElementById('detail-content');
        if (!content || this.currentTab !== 'status') return;

        const duration = status.duration_seconds
            ? `${Math.floor(status.duration_seconds / 60)}m ${status.duration_seconds % 60}s`
            : '—';

        const taskPreview = status.current_task_content
            ? `<div class="detail-preview">${escapeHtml(status.current_task_content)}</div>`
            : '<div class="detail-empty">No active task</div>';

        const outputPreview = status.latest_output
            ? `<div class="detail-output-card" onclick="AgentDetail.switchTab('outputs')">
                <div class="detail-output-name">${escapeHtml(status.latest_output.filename)}</div>
                <div class="detail-output-time">${timeAgo(status.latest_output.modified)}</div>
                <div class="detail-preview">${escapeHtml(status.latest_output.preview)}</div>
               </div>`
            : '<div class="detail-empty">No outputs yet</div>';

        content.innerHTML = `
            <div class="grid-2">
                <div>
                    <div class="detail-section">
                        <div class="detail-label">STATUS</div>
                        <div class="detail-row">
                            <span class="agent-state ${status.state}">${status.state}</span>
                            <span style="color:var(--text-dim);margin-left:8px;">Model: ${status.model}</span>
                        </div>
                    </div>
                    <div class="detail-section">
                        <div class="detail-label">WORKING ON</div>
                        <div class="detail-value">${status.current_task ? escapeHtml(status.current_task) : '—'}</div>
                    </div>
                    <div class="detail-section">
                        <div class="detail-label">DURATION</div>
                        <div class="detail-value">${duration}</div>
                    </div>
                    <div class="detail-section">
                        <div class="detail-label">PENDING TASKS</div>
                        <div class="detail-value">${status.task_count}</div>
                    </div>
                </div>
                <div>
                    <div class="detail-section">
                        <div class="detail-label">CURRENT TASK CONTENT</div>
                        ${taskPreview}
                    </div>
                    <div class="detail-section">
                        <div class="detail-label">LATEST OUTPUT</div>
                        ${outputPreview}
                    </div>
                </div>
            </div>
        `;
    },

    async refreshTasks() {
        if (!this.currentAgent) return;
        const tasks = await CrewHQ.getAgentTasks(this.currentAgent);
        const content = document.getElementById('detail-content');
        if (!content || this.currentTab !== 'tasks') return;

        if (!tasks.length) {
            content.innerHTML = `
                <div class="detail-empty" style="padding:40px;">No pending tasks</div>
                <div style="padding:16px;">
                    <button class="pixel-btn" onclick="showTaskModal('${this.currentAgent}')">ASSIGN NEW TASK</button>
                </div>`;
            return;
        }

        const taskRows = tasks.map((t, i) => `
            <div class="detail-task-item" data-filename="${escapeHtml(t.filename)}">
                <div class="detail-task-order">
                    ${i > 0 ? `<button class="detail-move-btn" onclick="AgentDetail.moveTask(${i}, ${i - 1})" title="Move up">▲</button>` : '<span class="detail-move-btn"></span>'}
                    ${i < tasks.length - 1 ? `<button class="detail-move-btn" onclick="AgentDetail.moveTask(${i}, ${i + 1})" title="Move down">▼</button>` : '<span class="detail-move-btn"></span>'}
                </div>
                <div class="detail-task-info" onclick="AgentDetail.viewTask('${escapeHtml(t.filename)}')">
                    <div class="detail-task-title">${escapeHtml(t.title)}</div>
                    <div class="detail-task-meta">${timeAgo(t.modified)} · ${t.size_kb}KB</div>
                </div>
                <button class="pixel-btn small danger" onclick="AgentDetail.cancelTask('${escapeHtml(t.filename)}')" title="Cancel task">✕</button>
            </div>
        `).join('');

        content.innerHTML = `
            <div class="detail-task-list">${taskRows}</div>
            <div style="padding:16px;border-top:2px solid var(--border);">
                <button class="pixel-btn" onclick="showTaskModal('${this.currentAgent}')">ASSIGN NEW TASK</button>
            </div>`;

        // Store task list for reordering
        this._taskList = tasks;
    },

    async viewTask(filename) {
        const result = await CrewHQ.getAgentTaskContent(this.currentAgent, filename);
        if (result.error) { showToast(result.error, true); return; }
        const { html, rendered } = renderMarkdown(result.content, filename);
        showModal(`
            <div class="modal-title">TASK: ${escapeHtml(filename)}</div>
            <div class="detail-preview${rendered ? ' md-rendered' : ''}" style="max-height:400px;overflow-y:auto;">${html}</div>
            <div class="modal-actions">
                <button class="pixel-btn secondary" onclick="closeModal()">CLOSE</button>
                <button class="pixel-btn danger" onclick="AgentDetail.cancelTask('${escapeHtml(filename)}');closeModal();">CANCEL TASK</button>
            </div>
        `);
    },

    async cancelTask(filename) {
        const result = await CrewHQ.cancelAgentTask(this.currentAgent, filename);
        if (result.ok) {
            showToast('Task cancelled');
            this.refreshTasks();
        } else {
            showToast(result.error || 'Failed', true);
        }
    },

    async moveTask(fromIdx, toIdx) {
        if (!this._taskList) return;
        const list = [...this._taskList];
        const [moved] = list.splice(fromIdx, 1);
        list.splice(toIdx, 0, moved);
        const filenames = list.map(t => t.filename);
        const result = await CrewHQ.reorderAgentTasks(this.currentAgent, filenames);
        if (result.ok) {
            this._taskList = list;
            this.refreshTasks();
        } else {
            showToast('Reorder failed', true);
        }
    },

    async refreshOutputs() {
        if (!this.currentAgent) return;
        const outputs = await CrewHQ.getAgentOutputs(this.currentAgent);
        const content = document.getElementById('detail-content');
        if (!content || this.currentTab !== 'outputs') return;

        if (!outputs.length) {
            content.innerHTML = '<div class="detail-empty" style="padding:40px;">No outputs yet</div>';
            return;
        }

        const rows = outputs.map(o => `
            <div class="detail-output-item" onclick="AgentDetail.viewOutput('${escapeHtml(o.filename)}')">
                <div class="detail-output-name">${escapeHtml(o.filename)}</div>
                <div class="detail-output-meta">${o.size_kb}KB · ${timeAgo(o.modified)}</div>
            </div>
        `).join('');

        content.innerHTML = `
            <div class="detail-output-list">${rows}</div>
            <div id="detail-output-viewer"></div>`;
    },

    async viewOutput(filename) {
        const result = await CrewHQ.getAgentOutputContent(this.currentAgent, filename);
        const viewer = document.getElementById('detail-output-viewer');
        if (!viewer) return;
        if (result.error) { showToast(result.error, true); return; }
        const { html, rendered } = renderMarkdown(result.content, filename);
        viewer.innerHTML = `
            <div class="detail-section" style="margin-top:12px;">
                <div class="detail-label">${escapeHtml(filename)}</div>
                <div class="detail-preview${rendered ? ' md-rendered' : ''}" style="max-height:400px;overflow-y:auto;">${html}</div>
            </div>`;
    },

    async refreshChat() {
        if (!this.currentAgent) return;
        const content = document.getElementById('detail-content');
        if (!content || this.currentTab !== 'chat') return;

        const history = await CrewHQ.getAgentChatHistory(this.currentAgent);
        const agent = (CrewHQ.state?.agents || []).find(a => a.id === this.currentAgent);
        const agentName = agent ? agent.name : this.currentAgent;
        const agentColor = agent ? agent.color : '#666';

        const msgs = history.map(m => {
            const sender = m.role === 'user' ? 'MANAGER' : agentName.toUpperCase();
            const cls = m.role === 'user' ? 'user' : 'assistant';
            const senderColor = m.role === 'user' ? 'var(--accent)' : agentColor;
            const time = m.time ? shortTime(m.time) : '';
            return `<div class="chat-msg ${cls}">
                <span class="chat-sender" style="color:${senderColor}">${sender}</span>
                <div>${escapeHtml(m.text)}</div>
                ${time ? `<div class="chat-time">${time}</div>` : ''}
            </div>`;
        }).join('');

        content.innerHTML = `
            <div class="detail-chat-container">
                <div class="detail-chat-messages" id="detail-chat-msgs">
                    ${msgs || `<div class="detail-empty">No messages yet. Start a conversation with ${agentName}.</div>`}
                </div>
                <div id="detail-chat-typing" class="chat-typing" style="display:none;">${agentName.toUpperCase()} IS THINKING...</div>
                <div class="chat-input-bar">
                    <input class="pixel-input" id="detail-chat-input" placeholder="Message ${agentName}..."
                        onkeydown="if(event.key==='Enter') AgentDetail.sendChat()">
                    <button class="pixel-btn" onclick="AgentDetail.sendChat()">SEND</button>
                </div>
            </div>`;

        // Scroll to bottom
        const msgsEl = document.getElementById('detail-chat-msgs');
        if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
    },

    async sendChat() {
        const input = document.getElementById('detail-chat-input');
        if (!input) return;
        const text = input.value.trim();
        if (!text) return;

        const agent = (CrewHQ.state?.agents || []).find(a => a.id === this.currentAgent);
        const agentName = agent ? agent.name : this.currentAgent;
        const agentColor = agent ? agent.color : '#666';

        // Show user message immediately
        const msgsEl = document.getElementById('detail-chat-msgs');
        if (msgsEl) {
            const emptyEl = msgsEl.querySelector('.detail-empty');
            if (emptyEl) emptyEl.remove();
            msgsEl.innerHTML += `<div class="chat-msg user">
                <span class="chat-sender" style="color:var(--accent)">MANAGER</span>
                <div>${escapeHtml(text)}</div>
                <div class="chat-time">${shortTime(new Date().toISOString())}</div>
            </div>`;
            msgsEl.scrollTop = msgsEl.scrollHeight;
        }

        input.value = '';
        const typingEl = document.getElementById('detail-chat-typing');
        if (typingEl) typingEl.style.display = 'block';

        const result = await CrewHQ.sendAgentChat(this.currentAgent, text);

        if (typingEl) typingEl.style.display = 'none';
        const reply = result.message || result.error || 'No response.';
        if (msgsEl) {
            msgsEl.innerHTML += `<div class="chat-msg assistant">
                <span class="chat-sender" style="color:${agentColor}">${agentName.toUpperCase()}</span>
                <div>${escapeHtml(reply)}</div>
                <div class="chat-time">${shortTime(new Date().toISOString())}</div>
            </div>`;
            msgsEl.scrollTop = msgsEl.scrollHeight;
        }
    },
};

// ── Init ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initNav();
    CrewHQ.connect();
});
