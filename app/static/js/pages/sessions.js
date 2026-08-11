// Sessions page: 14-day activity timeline (extracted from sessions.html, DESIGN.md 15.4).
(function () {
  'use strict';
  const canvas = document.getElementById('session-timeline');
  if (!canvas) return; // page module guards its root element
  (async () => {
    try {
      const res = await fetch('/api/v2/charts/activity?days=14');
      const data = await res.json();
      new Chart(canvas, {
        type: 'line',
        data: {
          labels: data.labels,
          datasets: [
            {
              label: 'Completed',
              data: data.completed,
              borderColor: '#2F7657',
              backgroundColor: 'rgba(47,118,87,0.1)',
              fill: true,
              tension: 0.3,
              pointRadius: 3,
              pointBackgroundColor: '#2F7657',
            },
            {
              label: 'Stopped',
              data: data.interrupted,
              borderColor: '#A83B4A',
              backgroundColor: 'rgba(168,59,74,0.06)',
              fill: true,
              tension: 0.3,
              pointRadius: 3,
              pointBackgroundColor: '#A83B4A',
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: '#94a3b8', usePointStyle: true, font: { size: 11 }, padding: 16 } },
            tooltip: { backgroundColor: '#1E293B', titleColor: '#F8FAFC', bodyColor: '#CBD5E1', padding: 8, cornerRadius: 6 },
          },
          scales: {
            x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } },
            y: { ticks: { color: '#94a3b8', stepSize: 1, font: { size: 10 } }, grid: { color: 'rgba(148,163,184,0.12)' } },
          },
          interaction: { intersect: false, mode: 'index' },
        },
      });
    } catch (e) {
      console.warn('Session timeline:', e);
    }
  })();
})();
