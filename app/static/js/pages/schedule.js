// Schedule page: today's rules + weekly timeline (extracted from schedule.html, DESIGN.md 15.4).
(function () {
  'use strict';
  const TYPE_COLORS = { mandatory: '#A83B4A', optional_mandatory: '#9A6415', optional: '#2F7657', penalty_reducing: '#356A9A' };

  let timelineChart = null;

  async function loadAll() {
    const todayRes = await fetch('/api/v2/schedule/today');
    const todayRules = await todayRes.json();
    const el = document.getElementById('today-sched');
    if (!todayRules.length) {
      el.innerHTML = '<p class="text-[color:var(--text-muted)] text-center py-4 text-sm">No rules for today.</p>';
    } else {
      el.innerHTML = todayRules
        .map(
          (r) => `
      <div class="flex items-center gap-3 p-2 rounded-lg border-l-4" style="border-left-color:${TYPE_COLORS[r.task_type] || '#94a3b8'}">
        <span class="text-xs font-mono text-[color:var(--text-muted)] w-24 tabular-nums">${r.start_time}${r.end_time ? ' – ' + r.end_time : ''}</span>
        <span class="flex-1 text-sm text-slate-700 dark:text-slate-300">${escapeHtml(String(r.entity_name || r.notes || '—'))}</span>
        <span class="text-xs px-2 py-0.5 rounded font-medium" style="background:${TYPE_COLORS[r.task_type]}18;color:${TYPE_COLORS[r.task_type]}">${escapeHtml(r.task_type)}</span>
      </div>
    `
        )
        .join('');
    }
    loadTimeline(todayRules);
  }

  function loadTimeline(todayRules) {
    const ctx = document.getElementById('week-timeline').getContext('2d');
    if (timelineChart) timelineChart.destroy();

    const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const byDay = {};
    for (const r of todayRules) {
      const dow = r.day_of_week === 7 ? 'all' : r.day_of_week;
      if (!byDay[dow]) byDay[dow] = [];
      byDay[dow].push(r);
    }

    const colorPalette = ['#6B57A5', '#2F7657', '#9A6415', '#A83B4A', '#356A9A', '#B8A3EE', '#71C89D'];
    const datasets = [];
    for (let dow = 0; dow < 7; dow++) {
      const rules = (byDay[dow] || []).concat(byDay['all'] || []);
      if (rules.length === 0) continue;
      datasets.push({
        label: dayLabels[dow],
        data: rules.map((r) => {
          const [sh, sm] = (r.start_time || '00:00').split(':').map(Number);
          const [eh, em] = (r.end_time || '23:59').split(':').map(Number);
          return { x: [sh * 60 + sm, eh * 60 + em], y: dayLabels[dow], name: r.entity_name || r.notes || '', type: r.task_type };
        }),
        backgroundColor: colorPalette[dow] + '99',
        borderColor: colorPalette[dow],
        borderWidth: 1,
        borderRadius: 4,
      });
    }

    timelineChart = new Chart(ctx, {
      type: 'bar',
      data: { datasets },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#94a3b8', font: { size: 10 }, usePointStyle: true, padding: 12 } },
          tooltip: {
            backgroundColor: '#1E293B',
            titleColor: '#F8FAFC',
            bodyColor: '#CBD5E1',
            padding: 8,
            cornerRadius: 6,
            callbacks: {
              label: (ctx) => {
                const d = ctx.raw;
                const sh = Math.floor(d.x[0] / 60), sm = d.x[0] % 60;
                const eh = Math.floor(d.x[1] / 60), em = d.x[1] % 60;
                return `${d.name || 'Rule'}: ${String(sh).padStart(2, '0')}:${String(sm).padStart(2, '0')} - ${String(eh).padStart(2, '0')}:${String(em).padStart(2, '0')}`;
              },
            },
          },
        },
        scales: {
          x: {
            type: 'linear',
            min: 0,
            max: 1440,
            ticks: { color: '#94a3b8', font: { size: 9 }, stepSize: 120, callback: (v) => `${Math.floor(v / 60)}:${String(v % 60).padStart(2, '0')}` },
            grid: { color: 'rgba(148,163,184,0.12)' },
          },
          y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } },
        },
      },
    });
  }

  function showForm() {
    document.getElementById('add-form').classList.toggle('hidden');
  }
  const schedForm = document.getElementById('sched-form');
  if (schedForm) {
    schedForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = {
        day_of_week: parseInt(document.getElementById('sched-dow').value),
        start_time: document.getElementById('sched-start').value,
        end_time: document.getElementById('sched-end').value || null,
        task_type: document.getElementById('sched-type').value,
        notes: document.getElementById('sched-notes').value || null,
        recurring: document.getElementById('sched-recur').checked,
      };
      const entity = document.getElementById('sched-entity').value.trim();
      if (entity) body.entity_name = entity;
      await fetch('/api/v2/schedule/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      document.getElementById('add-form').classList.add('hidden');
      loadAll();
    });
  }
  loadAll();

  window.showForm = showForm;
})();
