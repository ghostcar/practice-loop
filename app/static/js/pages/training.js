// Training page: completion chart, journal DnD reorder, photo reports, day timeline
// (extracted from training.html, DESIGN.md 15.4).
(function () {
  'use strict';

  // ── Completion trend chart ──
  const trendEl = document.getElementById('training-trend');
  if (trendEl) {
    (async () => {
      try {
        const res = await fetch('/api/v2/charts/completion-rate?days=7');
        const data = await res.json();
        new Chart(trendEl, {
          type: 'bar',
          data: {
            labels: data.labels,
            datasets: [
              {
                label: 'Completion %',
                data: data.rates,
                backgroundColor: data.rates.map((r) => (r >= 75 ? '#2F7657' : r >= 40 ? '#9A6415' : '#A83B4A')),
                borderRadius: 4,
                borderSkipped: false,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: '#1E293B',
                titleColor: '#F8FAFC',
                bodyColor: '#CBD5E1',
                padding: 8,
                cornerRadius: 6,
                callbacks: { label: (ctx) => ctx.raw + '%' },
              },
            },
            scales: {
              x: { ticks: { color: '#94a3b8', font: { size: 11 } }, grid: { display: false } },
              y: { ticks: { color: '#94a3b8', font: { size: 11 }, callback: (v) => v + '%' }, grid: { color: 'rgba(148,163,184,0.12)' }, max: 100 },
            },
          },
        });
      } catch (e) {
        console.warn('Training trend:', e);
      }
    })();
  }

  // ── Journal drag&drop reorder (native HTML5 DnD, per training day) ──
  (function () {
    let draggedId = null;
    document.querySelectorAll('[id^="log-entries-"]').forEach((list) => {
      list.addEventListener('dragstart', (e) => {
        const row = e.target.closest('.log-entry-row');
        if (!row) return;
        draggedId = row.dataset.entryId;
        row.classList.add('opacity-50');
        e.dataTransfer.effectAllowed = 'move';
      });
      list.addEventListener('dragend', (e) => {
        const row = e.target.closest('.log-entry-row');
        if (row) row.classList.remove('opacity-50');
        draggedId = null;
      });
      list.addEventListener('dragover', (e) => {
        e.preventDefault();
      });
      list.addEventListener('drop', (e) => {
        e.preventDefault();
        const target = e.target.closest('.log-entry-row');
        const trainingDayId = list.dataset.trainingDayId;
        if (!target || !draggedId || !trainingDayId || draggedId === target.dataset.entryId) return;
        const rows = Array.from(list.querySelectorAll('.log-entry-row'));
        const from = rows.findIndex((r) => r.dataset.entryId === draggedId);
        const to = rows.findIndex((r) => r.dataset.entryId === target.dataset.entryId);
        if (from < 0 || to < 0) return;
        const [moved] = rows.splice(from, 1);
        rows.splice(to, 0, moved);
        const ids = rows.map((r) => r.dataset.entryId);
        fetch('/training/log-entry/reorder', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ training_day_id: trainingDayId, ids: ids }),
        }).then((res) => {
          if (res.ok) location.reload();
        });
      });
    });
  })();

  // ── Photo reports (attachments on activity logs) ──
  let logPhotoTarget = null;
  function pickLogPhoto(logId) {
    logPhotoTarget = logId;
    document.getElementById('log-photo-input').click();
  }
  const photoInput = document.getElementById('log-photo-input');
  if (photoInput) {
    photoInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file || !logPhotoTarget) return;
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/attachments?owner_type=activity_log&owner_id=' + logPhotoTarget, {
        method: 'POST',
        body: fd,
      });
      logPhotoTarget = null;
      location.reload();
    });
  }

  async function loadLogPhotos() {
    document.querySelectorAll('.photo-thumbs').forEach(async (thumbs) => {
      const ownerType = thumbs.dataset.ownerType;
      const ownerId = thumbs.dataset.ownerId;
      const res = await fetch('/attachments?owner_type=' + ownerType + '&owner_id=' + ownerId);
      if (!res.ok) return;
      const atts = await res.json();
      thumbs.innerHTML = atts
        .map(
          (a) =>
            `<span class="relative group inline-block">` +
            `<img src="${escapeHtml(a.file_path)}" alt="" class="w-10 h-10 rounded object-cover border border-slate-200 dark:border-slate-700" loading="lazy">` +
            `<button type="button" onclick="delLogPhoto('${escapeHtml(a.id)}')" class="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[9px] leading-none hidden group-hover:flex items-center justify-center">✕</button>` +
            `</span>`
        )
        .join('');
    });
  }
  async function delLogPhoto(id) {
    await fetch('/attachments/' + id, { method: 'DELETE' });
    location.reload();
  }
  loadLogPhotos();

  // ── Day timeline rendering ──
  (function () {
    const dataEl = document.getElementById('timeline-data');
    const tracksEl = document.getElementById('timeline-tracks');
    if (!dataEl || !tracksEl) return;
    let blocks;
    try {
      blocks = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }
    if (!blocks.length) return;

    const DAY = 1440;
    // Greedy lane packing: assign each block to the first lane it fits in.
    const lanes = [];
    blocks.sort((a, b) => a.start - b.start);
    blocks.forEach((b) => {
      let lane = lanes.find((l) => l.every((x) => b.start >= x.end || b.end <= x.start));
      if (!lane) {
        lane = [];
        lanes.push(lane);
      }
      lane.push(b);
      b.lane = lanes.indexOf(lane);
    });

    const laneH = 28;
    tracksEl.style.height = lanes.length * laneH + 4 + 'px';
    const colors = { journal: '#6B57A5', schedule: '#2F7657' };
    blocks.forEach((b) => {
      const left = (b.start / DAY) * 100;
      const width = Math.max(((b.end - b.start) / DAY) * 100, 1.2);
      const div = document.createElement('div');
      div.className = 'absolute rounded-md px-2 py-0.5 text-[10px] font-medium text-white overflow-hidden whitespace-nowrap';
      div.style.left = left + '%';
      div.style.width = width + '%';
      div.style.top = b.lane * laneH + 2 + 'px';
      div.style.height = laneH - 4 + 'px';
      div.style.background = colors[b.kind] || '#64748b';
      div.title = (b.sub || b.kind) + ': ' + b.label + (b.value ? ' — ' + b.value : '');
      div.textContent = b.label + (b.value ? ' · ' + b.value : '');
      tracksEl.appendChild(div);
    });
  })();

  // Exposed for inline onclick handlers in the template.
  window.pickLogPhoto = pickLogPhoto;
  window.delLogPhoto = delLogPhoto;
})();
