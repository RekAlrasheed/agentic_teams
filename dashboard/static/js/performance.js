/* ═══════════════════════════════════════════════════════
   NAVAIA CREW HQ — Performance Dashboard
   ═══════════════════════════════════════════════════════ */

let perfData = null;
let currentPeriod = 14;
let currentKpiTab = 'all';

const AGENT_NAMES = {
    pm: 'Navi', creative: 'Muse', technical: 'Arch',
    admin: 'Sage', ceo: 'Rex',
};

const AGENT_COLORS = {
    pm: '#4a9eff', creative: '#ff8c42', technical: '#a855f7',
    admin: '#22c55e', ceo: '#f59e0b',
};

async function loadPerformance() {
    try {
        perfData = await CrewHQ.getPerformanceDashboard(currentPeriod);
        renderScorecards();
        renderTokenTrends();
        renderTaskMetrics();
        renderKPITable();
        renderEvalHistory();
    } catch (err) {
        console.error('Performance load error:', err);
    }
}

function switchPeriod(days) {
    currentPeriod = days;
    document.querySelectorAll('.period-btn').forEach(b => {
        b.classList.toggle('active', parseInt(b.dataset.days) === days);
    });
    loadPerformance();
}

// ── Scorecards ────────────────────────────────────────────

function renderScorecards() {
    const container = document.getElementById('scorecards');
    const scores = perfData?.scores || {};
    const agents = ['pm', 'creative', 'technical', 'admin', 'ceo'];

    const cards = agents.map(agent => {
        const data = scores[agent];
        const name = AGENT_NAMES[agent] || agent;
        const color = AGENT_COLORS[agent] || '#666';

        if (!data) {
            return `<div class="scorecard">
                <div class="agent-name" style="color:${color}">${name.toUpperCase()}</div>
                <div class="score-value" style="color:var(--text-dim)">--</div>
                <div class="score-trend stable">-</div>
                <div class="quality-stars" style="color:var(--text-dim)">No data</div>
            </div>`;
        }

        const trendIcon = data.trend === 'up' ? '&#9650;' : data.trend === 'down' ? '&#9660;' : '&#9644;';
        const stars = '&#9733;'.repeat(data.last_rating) + '&#9734;'.repeat(5 - data.last_rating);

        // Mini history bars from recent evaluations
        const agentEvals = (perfData?.recent_evaluations || [])
            .filter(e => e.agent === agent)
            .slice(0, 8)
            .reverse();

        const maxDelta = Math.max(1, ...agentEvals.map(e => Math.abs(e.score_delta)));
        const historyBars = agentEvals.map(e => {
            const h = Math.max(2, Math.abs(e.score_delta) / maxDelta * 20);
            const cls = e.score_delta > 0 ? 'positive' : e.score_delta < 0 ? 'negative' : 'neutral';
            return `<div class="bar ${cls}" style="height:${h}px"></div>`;
        }).join('');

        return `<div class="scorecard">
            <div class="agent-name" style="color:${color}">${name.toUpperCase()}</div>
            <div class="score-value">${data.score >= 0 ? '+' : ''}${data.score.toFixed(1)}</div>
            <div class="score-trend ${data.trend}">${trendIcon}</div>
            <div class="quality-stars">${stars}</div>
            <div class="score-history">${historyBars || '<span style="color:var(--text-dim);font-size:12px;">No history</span>'}</div>
        </div>`;
    }).join('');

    container.innerHTML = cards;
}

// ── Token Trends ──────────────────────────────────────────

function renderTokenTrends() {
    const container = document.getElementById('token-chart');
    const usage = perfData?.token_usage || {};
    const agents = Object.keys(usage);

    if (!agents.length) {
        container.innerHTML = '<div class="empty-state"><div class="message">NO TOKEN DATA</div></div>';
        return;
    }

    const maxTokens = Math.max(1, ...agents.map(a => usage[a].total_tokens));

    const bars = agents.map(a => {
        const d = usage[a];
        const pct = (d.total_tokens / maxTokens * 100).toFixed(1);
        const name = AGENT_NAMES[a] || a;
        const color = AGENT_COLORS[a] || '#666';
        return `<div class="bar-row">
            <div class="bar-label" style="color:${color}">${name.toUpperCase()}</div>
            <div class="bar-track">
                <div class="bar-fill" style="width:${pct}%;background:${color}"></div>
            </div>
            <div class="bar-value">${formatTokens(d.total_tokens)}</div>
        </div>`;
    }).join('');

    container.innerHTML = `<div class="bar-chart">${bars}</div>`;
}

function formatTokens(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

// ── Task Metrics ──────────────────────────────────────────

function renderTaskMetrics() {
    const container = document.getElementById('task-metrics');
    const metrics = perfData?.task_metrics || {};
    const agents = Object.keys(metrics);

    if (!agents.length) {
        container.innerHTML = '<div class="empty-state"><div class="message">NO TASK DATA</div></div>';
        return;
    }

    const maxTotal = Math.max(1, ...agents.map(a => metrics[a].total));

    const bars = agents.map(a => {
        const m = metrics[a];
        const name = AGENT_NAMES[a] || a;
        const color = AGENT_COLORS[a] || '#666';
        const donePct = (m.done / maxTotal * 100).toFixed(1);
        const failPct = (m.failed / maxTotal * 100).toFixed(1);
        return `<div class="bar-row">
            <div class="bar-label" style="color:${color}">${name.toUpperCase()}</div>
            <div class="bar-track">
                <div class="bar-fill" style="width:${donePct}%;background:var(--online);display:inline-block;"></div><div class="bar-fill" style="width:${failPct}%;background:var(--error);display:inline-block;"></div>
            </div>
            <div class="bar-value">${m.done}/${m.total} (${m.completion_pct}%)</div>
        </div>`;
    }).join('');

    container.innerHTML = `<div class="bar-chart">${bars}</div>
        <div style="margin-top:8px;font-size:13px;color:var(--text-dim);">
            <span style="color:var(--online);">&#9632;</span> Done
            <span style="color:var(--error);margin-left:10px;">&#9632;</span> Failed
        </div>`;
}

// ── KPI Table ─────────────────────────────────────────────

function renderKPITable() {
    const tabsContainer = document.getElementById('kpi-tabs');
    const tableContainer = document.getElementById('kpi-table-container');
    const kpis = perfData?.kpis || {};

    const allAgents = ['all', ...Object.keys(kpis)];
    const tabs = allAgents.map(a => {
        const label = a === 'all' ? 'ALL' : (AGENT_NAMES[a] || a).toUpperCase();
        const cls = currentKpiTab === a ? 'active' : '';
        return `<button class="kpi-tab ${cls}" onclick="switchKpiTab('${a}')">${label}</button>`;
    }).join('');
    tabsContainer.innerHTML = tabs;

    let rows = [];
    const agentsToShow = currentKpiTab === 'all' ? Object.keys(kpis) : [currentKpiTab];

    for (const agent of agentsToShow) {
        const items = kpis[agent] || [];
        for (const item of items) {
            const name = AGENT_NAMES[agent] || agent;
            const color = AGENT_COLORS[agent] || '#666';
            const statusCls = `status-${item.status}`;
            const actualStr = item.actual !== null ? item.actual.toFixed(1) : '--';
            rows.push(`<tr>
                <td style="color:${color};font-weight:bold;">${name}</td>
                <td>${item.kpi_name}</td>
                <td>${item.category}</td>
                <td>${item.target.toFixed(1)} ${item.unit}</td>
                <td>${actualStr} ${item.unit}</td>
                <td class="${statusCls}">${item.status.toUpperCase()}</td>
            </tr>`);
        }
    }

    if (!rows.length) {
        tableContainer.innerHTML = '<div class="empty-state"><div class="message">NO KPI DATA YET</div></div>';
        return;
    }

    tableContainer.innerHTML = `<table class="kpi-table">
        <thead><tr>
            <th>AGENT</th><th>KPI</th><th>TYPE</th><th>TARGET</th><th>ACTUAL</th><th>STATUS</th>
        </tr></thead>
        <tbody>${rows.join('')}</tbody>
    </table>`;
}

function switchKpiTab(tab) {
    currentKpiTab = tab;
    renderKPITable();
}

// ── Evaluation History ────────────────────────────────────

function renderEvalHistory() {
    const container = document.getElementById('eval-history');
    const evals = perfData?.recent_evaluations || [];

    if (!evals.length) {
        container.innerHTML = '<div class="empty-state"><div class="message">NO EVALUATIONS YET</div><div style="color:var(--text-dim);margin-top:8px;font-size:15px;">RL evaluations appear here after every 20 completed tasks</div></div>';
        return;
    }

    const items = evals.map(e => {
        const name = AGENT_NAMES[e.agent] || e.agent;
        const color = AGENT_COLORS[e.agent] || '#666';
        const deltaCls = e.score_delta > 0 ? 'positive' : e.score_delta < 0 ? 'negative' : '';
        const deltaStr = e.score_delta >= 0 ? `+${e.score_delta.toFixed(1)}` : e.score_delta.toFixed(1);
        const date = e.evaluated_at ? new Date(e.evaluated_at).toLocaleDateString() : '--';
        const summary = e.evaluation_summary || '--';

        return `<div class="eval-item">
            <div class="eval-batch">#${e.evaluation_batch}</div>
            <div class="eval-agent" style="background:${color};color:#000;">${name.toUpperCase()}</div>
            <div class="eval-summary" title="${summary}">${date} — ${summary}</div>
            <div class="eval-delta ${deltaCls}">${deltaStr}</div>
        </div>`;
    }).join('');

    container.innerHTML = items;
}

// ── Init ──────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    loadPerformance();
    // Refresh every 30 seconds
    setInterval(loadPerformance, 30000);
});
