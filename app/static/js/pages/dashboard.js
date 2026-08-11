// Dashboard v2: telegram linking, activity chart, category summary, points trend,
// completion summary, XP sparkline (extracted from dashboard_v2.html, DESIGN.md 15.4).
// i18n strings + tg_bot_username come from the <script type="application/json" id="page-i18n"> block.
(function () {
  'use strict';
  let T = {};
  try {
    const el = document.getElementById('page-i18n');
    if (el) T = JSON.parse(el.textContent) || {};
  } catch (e) {
    console.warn('Dashboard page i18n:', e);
  }
  const tgBotUser = T.tg_bot_username || '';

  // ── Telegram linking ──
  let tgLinked = false;
  const statusEl = document.getElementById('tg-status-text');
  const btnEl = document.getElementById('tg-link-btn');

  async function checkTelegramStatus() {
    try {
      const res = await fetch('/profile/telegram-status');
      const data = await res.json();
      tgLinked = data.linked;
      if (data.linked) {
        statusEl.textContent = T.dashboard_telegram_connected || '';
        btnEl.textContent = T.dashboard_open_bot || '';
        btnEl.onclick = () => window.open('https://t.me/' + tgBotUser, '_blank');
      } else if (data.code) {
        statusEl.textContent = T.dashboard_telegram_code_ready || '';
        showCode(data.code);
      } else {
        statusEl.textContent = T.dashboard_telegram_not_linked || '';
      }
    } catch (e) {
      console.warn('TG status:', e);
    }
  }

  async function generateLinkCode() {
    if (tgLinked) {
      window.open('https://t.me/' + tgBotUser, '_blank');
      return;
    }
    try {
      const res = await fetch('/profile/telegram-link-code', { method: 'POST' });
      const data = await res.json();
      showCode(data.code);
      statusEl.textContent = T.dashboard_telegram_code_ready || '';
    } catch (e) {
      console.warn('TG code:', e);
    }
  }

  function showCode(code) {
    document.getElementById('tg-code').textContent = code;
    document.getElementById('tg-code-display').classList.remove('hidden');
    btnEl.textContent = T.dashboard_new_code || '';
  }

  // ── Color palette (DESIGN.md semantic tokens) ──
  const PALETTE = ['#6B57A5', '#2F7657', '#9A6415', '#A83B4A', '#356A9A', '#B8A3EE', '#71C89D', '#E4B064'];
  const CHART_GRID = 'rgba(148,163,184,0.12)';
  const CHART_TEXT = '#94a3b8';
  const FONT = 'Inter, system-ui, sans-serif';

  Chart.defaults.font.family = FONT;
  Chart.defaults.font.size = 11;

  const root = document.getElementById('activity-chart');
  if (!root) return;

  document.addEventListener('DOMContentLoaded', async () => {
    checkTelegramStatus();

    // ── Weekly Activity Bar Chart ──
    try {
      const res = await fetch('/api/v2/charts/activity?days=7');
      const data = await res.json();
      new Chart(document.getElementById('activity-chart'), {
        type: 'bar',
        data: {
          labels: data.labels,
          datasets: [
            { label: T.dashboard_chart_done || '', data: data.completed, backgroundColor: '#2F7657', borderRadius: 4, borderSkipped: false },
            { label: T.dashboard_chart_stop || '', data: data.interrupted, backgroundColor: '#A83B4A', borderRadius: 4, borderSkipped: false },
            { label: T.dashboard_chart_pending || '', data: data.pending, backgroundColor: '#E1DFE7', borderRadius: 4, borderSkipped: false },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { stacked: true, ticks: { color: CHART_TEXT, font: { size: 10 } }, grid: { display: false } },
            y: { stacked: true, ticks: { color: CHART_TEXT, stepSize: 1, font: { size: 10 } }, grid: { color: CHART_GRID }, beginAtZero: true },
          },
          interaction: { intersect: false, mode: 'index' },
        },
      });
    } catch (e) {
      console.warn('Activity chart:', e);
    }

    // ── Category Summary (replaces 4th chart, DESIGN.md §11) ──
    try {
      const catRes = await fetch('/api/v2/charts/category-breakdown?days=30');
      const catData = await catRes.json();
      const colors = PALETTE.slice(0, Math.max(catData.labels.length, 1));
      const total = catData.values.reduce((a, b) => a + b, 0);
      const el = document.getElementById('category-summary');
      if (total === 0) {
        el.innerHTML =
          '<p class="text-sm text-slate-400 dark:text-slate-500">' +
          escapeHtml(T.dashboard_no_categories || '') +
          ' <a href="/entities/catalog" class="text-indigo-500 underline">' +
          escapeHtml(T.dashboard_browse_catalog || '') +
          '</a>.</p>';
      } else {
        // Show top-3 in compact form. Remaining: small "+N others" line.
        const entries = catData.labels
          .map((l, i) => ({ label: l, value: catData.values[i], color: colors[i] }))
          .sort((a, b) => b.value - a.value);
        const top3 = entries.slice(0, 3);
        const rest = entries.length - top3.length;
        el.innerHTML =
          top3
            .map((e) => {
              const pct = total ? Math.round((e.value / total) * 100) : 0;
              return `
                <div class="flex items-center gap-3">
                    <span class="w-2.5 h-2.5 rounded-sm flex-shrink-0" style="background:${e.color}" aria-hidden="true"></span>
                    <span class="text-sm text-slate-600 dark:text-slate-300 truncate flex-1 min-w-0">${escapeHtml(e.label)}</span>
                    <span class="text-xs text-slate-400 tabular-nums">${e.value}  ·  ${pct}%</span>
                </div>`;
            })
            .join('') + (rest > 0 ? `<div class="text-xs text-slate-400 pt-1">+ ${rest} ${escapeHtml(T.dashboard_others || '')}</div>` : '');
      }
    } catch (e) {
      console.warn('Category summary:', e);
    }

    // ── Points Trend (30 days) ──
    try {
      const ptsRes = await fetch('/api/v2/charts/points-trend?days=30');
      const ptsData = await ptsRes.json();
      const ctx = document.getElementById('points-trend-chart').getContext('2d');
      const gradient = ctx.createLinearGradient(0, 0, 0, 300);
      gradient.addColorStop(0, 'rgba(107,87,165,0.25)');
      gradient.addColorStop(1, 'rgba(107,87,165,0.02)');
      new Chart(ctx, {
        type: 'line',
        data: {
          labels: ptsData.labels,
          datasets: [
            {
              data: ptsData.balance,
              borderColor: '#6B57A5',
              borderWidth: 2,
              backgroundColor: gradient,
              fill: true,
              tension: 0.3,
              pointRadius: 0,
              pointHitRadius: 8,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: CHART_TEXT, font: { size: 10 }, maxTicksLimit: 6, maxRotation: 0 }, grid: { display: false } },
            y: { ticks: { color: CHART_TEXT, font: { size: 10 } }, grid: { color: CHART_GRID } },
          },
          interaction: { intersect: false, mode: 'index' },
        },
      });
      const lastBalance = ptsData.balance.length ? ptsData.balance[ptsData.balance.length - 1] : 0;
      document.getElementById('stat-points').textContent = lastBalance;
    } catch (e) {
      console.warn('Points trend:', e);
    }

    // ── Completion Rate Summary (replaces 4th chart, DESIGN.md §11) ──
    try {
      const rateRes = await fetch('/api/v2/charts/completion-rate?days=7');
      const rateData = await rateRes.json();
      const rate = rateData.overall_rate;
      const big = document.getElementById('completion-rate-big');
      big.textContent = rate + '%';
      big.style.color = rate >= 75 ? '#2F7657' : rate >= 40 ? '#9A6415' : '#A83B4A';
      document.getElementById('completion-stats').innerHTML =
        `<div class="flex justify-between"><span>${escapeHtml(T.dashboard_completion_completed || '')}</span><span class="font-medium text-emerald-600 dark:text-emerald-400 tabular-nums">${rateData.completed_tasks}</span></div>
             <div class="flex justify-between"><span>${escapeHtml(T.dashboard_completion_total || '')}</span><span class="font-medium text-slate-700 dark:text-slate-300 tabular-nums">${rateData.total_tasks}</span></div>`;
    } catch (e) {
      console.warn('Completion summary:', e);
    }

    // ── XP Sparkline ──
    try {
      const xpRes = await fetch('/api/v2/charts/xp-history?days=7');
      const xpData = await xpRes.json();
      new Chart(document.getElementById('xp-sparkline'), {
        type: 'line',
        data: {
          labels: xpData.labels,
          datasets: [
            { data: xpData.values, borderColor: '#818cf8', borderWidth: 2, fill: true, backgroundColor: 'rgba(129,140,248,0.12)', tension: 0.3, pointRadius: 0 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { x: { display: false }, y: { display: false, beginAtZero: true } },
        },
      });
    } catch (e) {
      console.warn('XP sparkline:', e);
    }
  });

  // Exposed for inline onclick handlers in the template.
  window.generateLinkCode = generateLinkCode;
})();
