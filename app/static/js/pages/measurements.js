// Measurements page: table, chart, trend indicator (extracted from measurements.html, DESIGN.md 15.4).
(function () {
  'use strict';
  let chart;
  Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
  Chart.defaults.font.size = 11;

  function parseFloatOrNull(id) {
    const v = document.getElementById(id).value;
    return v ? parseFloat(v) : null;
  }

  async function loadMeasurements() {
    const res = await fetch('/api/v2/measurements?limit=60');
    const data = await res.json();
    document.getElementById('meas-table').innerHTML =
      data
        .map(
          (m) =>
            `<tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
      <td class="px-4 py-2 text-slate-700 dark:text-slate-300">${escapeHtml(String(m.measured_date))}</td>
      <td class="px-4 py-2 text-slate-500 dark:text-slate-400">${escapeHtml(m.time_of_day)}</td>
      <td class="px-4 py-2 text-right text-slate-700 dark:text-slate-300 tabular-nums">${m.weight ?? '—'}</td>
      <td class="px-4 py-2 text-right text-slate-700 dark:text-slate-300 tabular-nums">${m.chest ?? '—'}</td>
      <td class="px-4 py-2 text-right text-slate-700 dark:text-slate-300 tabular-nums">${m.waist ?? '—'}</td>
      <td class="px-4 py-2 text-right text-slate-700 dark:text-slate-300 tabular-nums">${m.hips ?? '—'}</td>
      <td class="px-4 py-2 text-right text-slate-700 dark:text-slate-300 tabular-nums">${m.thigh ?? '—'}</td>
    </tr>`
        )
        .join('') ||
      '<tr><td colspan="7" class="px-4 py-8 text-center text-slate-400">No measurements yet</td></tr>';
  }

  async function loadChart(metric) {
    document.querySelectorAll('.chart-btn').forEach((b) => {
      b.classList.remove('bg-indigo-600', 'text-white');
      b.classList.add('bg-slate-100', 'dark:bg-slate-800');
    });
    event.target.classList.add('bg-indigo-600', 'text-white');
    event.target.classList.remove('bg-slate-100', 'dark:bg-slate-800');
    const res = await fetch(`/api/v2/measurements/charts?metric=${metric}&limit=60`);
    const data = await res.json();
    const ctx = document.getElementById('meas-chart').getContext('2d');
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.labels,
        datasets: [
          { label: 'Morning', data: data.morning, borderColor: '#6B57A5', backgroundColor: 'rgba(107,87,165,0.08)', fill: true, tension: 0.3, pointRadius: 2, spanGaps: true },
          { label: 'Evening', data: data.evening, borderColor: '#356A9A', backgroundColor: 'rgba(53,106,154,0.06)', fill: true, tension: 0.3, pointRadius: 2, spanGaps: true },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { labels: { color: '#94a3b8', usePointStyle: true, padding: 16, font: { size: 11 } } },
          tooltip: { backgroundColor: '#1E293B', titleColor: '#F8FAFC', bodyColor: '#CBD5E1', padding: 8, cornerRadius: 6 },
        },
        scales: {
          x: { ticks: { color: '#94a3b8', maxTicksLimit: 12, font: { size: 10 } }, grid: { display: false } },
          y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: 'rgba(148,163,184,0.12)' } },
        },
      },
    });

    const morningVals = data.morning.filter((v) => v !== null);
    if (morningVals.length >= 2) {
      const first = morningVals.slice(0, 3).reduce((a, b) => a + (b || 0), 0) / 3;
      const last = morningVals.slice(-3).reduce((a, b) => a + (b || 0), 0) / 3;
      const delta = last - first;
      const indicator = document.getElementById('trend-indicator');
      if (Math.abs(delta) < 0.5) {
        indicator.textContent = 'stable';
        indicator.className = 'text-xs px-2 py-1 rounded-full font-medium bg-slate-100 dark:bg-slate-800 text-slate-500';
      } else if ((metric === 'weight' && delta < 0) || (metric !== 'weight' && delta > 0)) {
        indicator.textContent = 'improving';
        indicator.className = 'text-xs px-2 py-1 rounded-full font-medium bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300';
      } else {
        indicator.textContent = 'watch it';
        indicator.className = 'text-xs px-2 py-1 rounded-full font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300';
      }
    }
  }

  document.getElementById('meas-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
      measured_date: document.getElementById('meas-date').value,
      time_of_day: document.getElementById('meas-tod').value,
      weight: parseFloatOrNull('meas-weight'),
      chest: parseFloatOrNull('meas-chest'),
      under_chest: parseFloatOrNull('meas-ucherst'),
      waist: parseFloatOrNull('meas-waist'),
      hips: parseFloatOrNull('meas-hips'),
      thigh: parseFloatOrNull('meas-thigh'),
    };
    await fetch('/api/v2/measurements', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    loadMeasurements();
  });
  document.getElementById('meas-date').value = new Date().toISOString().split('T')[0];
  loadMeasurements();
  loadChart('weight');

  // Exposed for inline onclick handlers in the template.
  window.loadChart = loadChart;
})();
