// Inventory page: list, filters, DnD reorder, photos, chart (extracted from inventory.html, DESIGN.md 15.4).
// i18n strings come from the <script type="application/json" id="page-i18n"> block.
(function () {
  'use strict';
  let T = {};
  try {
    const el = document.getElementById('page-i18n');
    if (el) T = JSON.parse(el.textContent) || {};
  } catch (e) {
    console.warn('Inventory page i18n:', e);
  }
  const I18N = {
    inv_qty_label: T.inv_qty_label || 'Qty',
    inv_priority_label: T.inv_priority_label || 'Priority',
    inv_empty: T.inv_empty || 'No items yet.',
    inv_btn_delete: T.calendar_btn_delete || 'Delete',
    inv_mark_shopping: T.inv_mark_shopping || 'Shopping',
    inv_items_counter_suffix: T.inv_items_counter_suffix || 'items',
    inv_status_need: T.inv_status_need || 'Need',
    inv_status_ordered: T.inv_status_ordered || 'Ordered',
    inv_status_bought: T.inv_status_bought || 'Bought',
    inv_status_built: T.inv_status_built || 'Built',
  };
  const STATUS_LABEL = {
    need: I18N.inv_status_need,
    ordered: I18N.inv_status_ordered,
    bought: I18N.inv_status_bought,
    built: I18N.inv_status_built,
  };

  const root = document.getElementById('inv-list');
  if (!root) return;

  let currentFilter = '';
  let invItems = [];
  let dragItemId = null;

  async function loadInventory(cat, shopOnly) {
    let url = '/api/v2/inventory?';
    if (cat) url += 'category=' + cat + '&';
    if (shopOnly) url += 'shopping_list=true&';
    const res = await fetch(url);
    invItems = await res.json();
    renderInventory();
  }

  function renderInventory() {
    const el = document.getElementById('inv-list');
    el.innerHTML =
      invItems
        .map(
          (i) => `
    <div class="bg-white dark:bg-slate-900 rounded-lg p-4 flex items-center gap-3 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 transition-colors cursor-grab" draggable="true" data-id="${escapeHtml(String(i.id))}">
      <span class="text-slate-300 dark:text-slate-600 select-none">⠿</span>
      ${i.image_path ? `<img src="${escapeHtml(i.image_path)}" alt="" class="w-12 h-12 rounded-lg object-cover flex-shrink-0 border border-slate-200 dark:border-slate-700" loading="lazy">` : ''}
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs px-2 py-0.5 rounded font-medium ${catBadge(escapeHtml(i.category))}">${escapeHtml(i.category)}</span>
          <span class="font-medium text-slate-800 dark:text-slate-100">${escapeHtml(i.name)}</span>
          <span class="text-xs font-medium ${statusBadge(escapeHtml(i.status))}">${escapeHtml(STATUS_LABEL[i.status] || i.status)}</span>
          ${i.is_shopping_list ? `<span class="text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded font-medium">${escapeHtml(I18N.inv_mark_shopping)}</span>` : ''}
        </div>
        <div class="text-xs text-slate-400 mt-1">${escapeHtml(I18N.inv_qty_label)}: ${i.quantity}/${i.quantity_needed} &middot; ${escapeHtml(I18N.inv_priority_label)}: ${i.priority}</div>
      </div>
      <div class="flex items-center gap-1 flex-shrink-0">
        <button onclick="pickImage('${escapeHtml(String(i.id))}')" class="text-slate-400 hover:text-indigo-500 text-sm px-2" title="Photo">📷</button>
        ${i.image_path ? `<button onclick="delImage('${escapeHtml(String(i.id))}')" class="text-slate-400 hover:text-red-500 text-sm px-2" title="Remove photo">✕</button>` : ''}
        <button onclick="del('${escapeHtml(String(i.id))}')" class="text-red-400 hover:text-red-500 text-sm px-2">${escapeHtml(I18N.inv_btn_delete)}</button>
      </div>
    </div>
  `
        )
        .join('') || '<p class="text-slate-400 dark:text-slate-500 text-center py-8">' + escapeHtml(I18N.inv_empty) + '</p>';
  }

  // Drag&drop reorder
  function bindDrag() {
    const list = document.getElementById('inv-list');
    list.addEventListener('dragstart', (e) => {
      const row = e.target.closest('[data-id]');
      if (!row) return;
      dragItemId = row.dataset.id;
      row.classList.add('opacity-50');
      e.dataTransfer.effectAllowed = 'move';
    });
    list.addEventListener('dragend', (e) => {
      const row = e.target.closest('[data-id]');
      if (row) row.classList.remove('opacity-50');
      dragItemId = null;
    });
    list.addEventListener('dragover', (e) => {
      e.preventDefault();
    });
    list.addEventListener('drop', async (e) => {
      e.preventDefault();
      const target = e.target.closest('[data-id]');
      if (!target || !dragItemId || dragItemId === target.dataset.id) return;
      const rows = Array.from(list.querySelectorAll('[data-id]'));
      const from = rows.findIndex((r) => r.dataset.id === dragItemId);
      const to = rows.findIndex((r) => r.dataset.id === target.dataset.id);
      if (from < 0 || to < 0) return;
      const [moved] = rows.splice(from, 1);
      rows.splice(to, 0, moved);
      const ids = rows.map((r) => r.dataset.id);
      await fetch('/api/v2/inventory/reorder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: ids }),
      });
      loadInventory(currentFilter, false);
    });
  }

  // Image upload
  let imgTargetId = null;
  function pickImage(id) {
    imgTargetId = id;
    document.getElementById('inv-img-input').click();
  }
  const imgInput = document.getElementById('inv-img-input');
  if (imgInput) {
    imgInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file || !imgTargetId) return;
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/v2/inventory/' + imgTargetId + '/image', { method: 'POST', body: fd });
      imgTargetId = null;
      if (res.ok) loadInventory(currentFilter, false);
    });
  }
  async function delImage(id) {
    await fetch('/api/v2/inventory/' + id + '/image', { method: 'DELETE' });
    loadInventory(currentFilter, false);
  }
  function catBadge(c) {
    const m = {
      clothing: 'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300',
      equipment: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
      cosmetics: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
      other: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
    };
    return m[c] || 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
  }
  function statusBadge(s) {
    const m = {
      need: 'text-red-600 dark:text-red-400',
      ordered: 'text-amber-600 dark:text-amber-400',
      bought: 'text-emerald-600 dark:text-emerald-400',
      built: 'text-emerald-600 dark:text-emerald-400',
    };
    return m[s] || 'text-slate-400';
  }
  function filter(c) {
    currentFilter = c;
    document.querySelectorAll('.filter-btn').forEach((b) => b.classList.remove('bg-indigo-600'));
    event.target.classList.add('bg-indigo-600');
    loadInventory(c, false);
  }
  function filterShoppingList() {
    document.querySelectorAll('.filter-btn').forEach((b) => b.classList.remove('bg-indigo-600'));
    event.target.classList.add('bg-indigo-600');
    loadInventory('', true);
  }
  function showForm() {
    document.getElementById('add-form').classList.toggle('hidden');
  }
  async function del(id) {
    await fetch('/api/v2/inventory/' + id, { method: 'DELETE' });
    loadInventory(currentFilter, false);
  }
  const invForm = document.getElementById('inv-form');
  if (invForm) {
    invForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = {
        category: document.getElementById('inv-cat').value,
        name: document.getElementById('inv-name').value,
        quantity: parseInt(document.getElementById('inv-qty').value) || 1,
        quantity_needed: parseInt(document.getElementById('inv-qtyn').value) || 1,
        status: document.getElementById('inv-status').value,
        priority: parseInt(document.getElementById('inv-prio').value) || 0,
        is_shopping_list: document.getElementById('inv-shop').checked,
      };
      await fetch('/api/v2/inventory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      document.getElementById('add-form').classList.add('hidden');
      loadInventory(currentFilter, false);
    });
  }
  bindDrag();
  loadInventory('', false);

  // Category chart
  (async () => {
    try {
      const res = await fetch('/api/v2/inventory');
      const items = await res.json();
      document.getElementById('inv-total').textContent = items.length + ' ' + escapeHtml(I18N.inv_items_counter_suffix);
      const cats = {};
      items.forEach((i) => {
        cats[i.category] = (cats[i.category] || 0) + 1;
      });
      const colors = { clothing: '#ec4899', equipment: '#3b82f6', cosmetics: '#a855f7', other: '#6b7280' };
      const ctx = document.getElementById('inv-chart').getContext('2d');
      new Chart(ctx, {
        type: 'bar',
        data: {
          labels: Object.keys(cats).map((c) => c.charAt(0).toUpperCase() + c.slice(1)),
          datasets: [
            {
              data: Object.values(cats),
              backgroundColor: Object.keys(cats).map((c) => colors[c] || '#6b7280'),
              borderRadius: 6,
            },
          ],
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#9ca3af', font: { size: 10 } }, grid: { color: '#374151' } },
            y: { ticks: { color: '#9ca3af', font: { size: 10 } }, grid: { display: false } },
          },
        },
      });
    } catch (e) {
      console.warn('Inv chart failed:', e);
    }
  })();

  // Exposed for inline onclick handlers in the template.
  window.del = del;
  window.delImage = delImage;
  window.filter = filter;
  window.filterShoppingList = filterShoppingList;
  window.pickImage = pickImage;
  window.showForm = showForm;
})();
