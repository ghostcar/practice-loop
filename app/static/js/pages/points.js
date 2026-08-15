// Points page: balance, thresholds, transactions, redemptions, profiles, charts
// (extracted from points.html, DESIGN.md 15.4).
(function () {
  'use strict';

  async function loadBalance() {
    const res = await fetch('/api/v2/points/balance');
    const d = await res.json();
    document.getElementById('bal-points').textContent = d.points_balance;
    document.getElementById('bal-xp').textContent = d.xp;
    document.getElementById('bal-lvl').textContent = d.level;

    // Thresholds
    if (d.thresholds) {
      document.getElementById('thresholds').innerHTML = `
      <div class="px-4 py-2 rounded-lg ${d.points_balance < d.thresholds.negative ? 'bg-red-900 ring-2 ring-red-500' : 'bg-gray-700'}">
        <span class="text-xs text-[color:var(--text-muted)]">Negative</span><br>&lt; ${d.thresholds.negative}
      </div>
      <div class="px-4 py-2 rounded-lg ${d.points_balance < d.thresholds.warning ? 'bg-yellow-900 ring-2 ring-yellow-500' : 'bg-gray-700'}">
        <span class="text-xs text-[color:var(--text-muted)]">Warning</span><br>&lt; ${d.thresholds.warning}
      </div>
      <div class="px-4 py-2 rounded-lg ${d.points_balance >= d.thresholds.good ? 'bg-green-900 ring-2 ring-green-500' : 'bg-gray-700'}">
        <span class="text-xs text-[color:var(--text-muted)]">Good</span><br>≥ ${d.thresholds.good}
      </div>
    `;
    }

    // Transactions
    document.getElementById('txn-table').innerHTML =
      d.recent_transactions
        .map(
          (t) => `
    <tr class="border-t border-slate-100 dark:border-slate-800">
      <td class="px-4 py-2 text-[color:var(--text-muted)] text-xs">${window.localDateISO(t.created_at)}</td>
      <td class="px-4 py-2 ${t.amount >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'}">${t.amount >= 0 ? '+' : ''}${t.amount}</td>
      <td class="px-4 py-2"><span class="text-xs px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800">${escapeHtml(t.transaction_type)}</span></td>
      <td class="px-4 py-2 text-slate-600 dark:text-slate-300">${escapeHtml(t.reason || '')}</td>
    </tr>
  `
        )
        .join('') || '<tr><td class="px-4 py-4 text-[color:var(--text-muted)] text-center" colspan="4">No transactions yet</td></tr>';
  }

  const spendForm = document.getElementById('spend-form');
  if (spendForm) {
    spendForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const amt = document.getElementById('spend-amt').value;
      const reason = document.getElementById('spend-reason').value;
      await fetch(`/api/v2/points/spend?amount=${amt}&reason=${encodeURIComponent(reason)}`, { method: 'POST' });
      loadBalance();
    });
  }

  async function loadRedemptions() {
    const res = await fetch('/api/v2/points/redemptions?status=pending');
    const data = await res.json();
    const el = document.getElementById('redemption-list');
    if (!data.length) {
      el.innerHTML = '<p class="text-xs text-[color:var(--text-muted)] py-1">No pending redemptions</p>';
      return;
    }
    el.innerHTML = data
      .map(
        (r) => `
    <div class="flex items-center justify-between p-2 rounded-lg border border-slate-200 dark:border-slate-800">
      <div class="flex-1">
        <span class="text-sm font-medium text-slate-800 dark:text-slate-200">${escapeHtml(r.redemption_type.replace(/_/g, ' '))}</span>
        <span class="text-xs text-[color:var(--text-muted)] ml-2">${r.duration_min}m ×${r.escalation_level}</span>
        ${r.description ? `<div class="text-xs text-slate-500">${escapeHtml(r.description)}</div>` : ''}
      </div>
      <div class="flex gap-1">
        <button onclick="completeRedemption('${r.id}')" class="text-xs px-2 py-1 rounded bg-emerald-700 hover:bg-emerald-600">+${r.points_value}pts</button>
        <button onclick="skipRedemption('${r.id}')" class="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600">Skip</button>
      </div>
    </div>
  `
      )
      .join('');
  }
  async function completeRedemption(id) {
    await fetch(`/api/v2/points/redemptions/${id}/complete`, { method: 'POST' });
    loadRedemptions();
    loadBalance();
  }
  async function skipRedemption(id) {
    await fetch(`/api/v2/points/redemptions/${id}/skip`, { method: 'POST' });
    loadRedemptions();
  }
  async function loadProfiles() {
    const res = await fetch('/api/v2/points/profiles');
    const profiles = await res.json();
    document.getElementById('profile-list').innerHTML =
      profiles
        .map(
          (p) =>
            `<div class="flex justify-between items-center"><span>${escapeHtml(p.name)} ${p.is_default ? '(default)' : ''}</span><button onclick="delProfile('${escapeHtml(String(p.id))}')" class="text-red-700 dark:text-red-400 hover:text-red-500">Del</button></div>`
        )
        .join('') || '<span class="text-[color:var(--text-muted)]">No profiles</span>';
    const sel = document.getElementById('assign-profile');
    sel.innerHTML = profiles.map((p) => `<option value="${escapeHtml(String(p.id))}">${escapeHtml(p.name)}</option>`).join('');
  }
  function showProfileForm() {
    document.getElementById('profile-form').classList.toggle('hidden');
  }
  async function saveProfile() {
    const name = document.getElementById('prof-name').value;
    await fetch('/api/v2/points/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        config: {
          points: { base: 10, max_per_day: 50 },
          penalties: { enabled: true, levels: [{ level: 1, deduction: 5, condition: 'missed' }] },
          bonuses: [],
          thresholds: { negative: -100, warning: 0, good: 100 },
        },
      }),
    });
    loadProfiles();
    document.getElementById('profile-form').classList.add('hidden');
  }
  async function delProfile(id) {
    await fetch(`/api/v2/points/profiles/${id}`, { method: 'DELETE' });
    loadProfiles();
  }

  const assignForm = document.getElementById('assign-form');
  if (assignForm) {
    assignForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const entityId = document.getElementById('assign-entity').value;
      const profileId = document.getElementById('assign-profile').value;
      await fetch(`/api/v2/entities/${entityId}/assign-profile?profile_id=${profileId}`, { method: 'POST' });
      alert('Profile assigned!');
    });
  }

  loadRedemptions();
  loadProfiles();
  loadBalance();

  // Trend chart
  (async () => {
    try {
      const res = await fetch('/api/v2/charts/points-trend?days=30');
      const data = await res.json();

      const ctx1 = document.getElementById('trend-chart').getContext('2d');
      new Chart(ctx1, {
        type: 'line',
        data: {
          labels: data.labels,
          datasets: [
            {
              label: 'Balance',
              data: data.balance,
              borderColor: '#818cf8',
              backgroundColor: 'rgba(129,140,248,0.1)',
              fill: true,
              tension: 0.3,
              pointRadius: 2,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: { legend: { labels: { color: '#9ca3af' } } },
          scales: {
            x: { ticks: { color: '#9ca3af', maxTicksLimit: 10, font: { size: 10 } }, grid: { display: false } },
            y: { ticks: { color: '#9ca3af', font: { size: 10 } }, grid: { color: '#374151' } },
          },
        },
      });

      const ctx2 = document.getElementById('donut-chart').getContext('2d');
      const breakdown = data.breakdown || {};
      const colors = { earn: '#10b981', penalty: '#ef4444', spend: '#f59e0b', redeem: '#6366f1', bonus: '#8b5cf6' };
      new Chart(ctx2, {
        type: 'doughnut',
        data: {
          labels: Object.keys(breakdown).map((k) => k.charAt(0).toUpperCase() + k.slice(1)),
          datasets: [
            {
              data: Object.values(breakdown),
              backgroundColor: Object.keys(breakdown).map((k) => colors[k] || '#6b7280'),
              borderColor: '#1f2937',
              borderWidth: 2,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: { legend: { labels: { color: '#9ca3af', font: { size: 11 } } } },
        },
      });
    } catch (e) {
      console.warn('Chart load failed:', e);
    }
  })();

  // Exposed for inline onclick handlers in the template.
  window.completeRedemption = completeRedemption;
  window.skipRedemption = skipRedemption;
  window.delProfile = delProfile;
  window.showProfileForm = showProfileForm;
  window.saveProfile = saveProfile;
})();
