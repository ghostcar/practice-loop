// Inventory page: 1C/ERP Nomenklatura Master Data catalog.
(function () {
  'use strict';
  let T = {};
  try {
    const el = document.getElementById('page-i18n');
    if (el) T = JSON.parse(el.textContent) || {};
  } catch (e) {
    console.warn('Inventory page i18n:', e);
  }

  const GROUP_LABELS = {
    equipment: '⚙️ Снаряжение & Инвентарь',
    wear: '👗 Экипировка & Одежда',
    care_cosmetics: '🧴 Уход & Косметика',
    electronics: '🔌 Девайсы & Электроника',
    furniture: '🛋️ Мебель & Фиксация',
    general: '📝 Общий справочник'
  };

  const INV_STATUS_LABEL = {
    available: '🟢 В наличии (Готов)',
    in_use: '🔵 В работе',
    cleaning: '🟡 На дезинфекции',
    charging: '⚡ На зарядке',
    maintenance: '🔧 На обслуживании',
    archived: '📦 В архиве',
    unavailable: '🔴 Недоступен'
  };

  let invCategories = [];
  const root = document.getElementById('inv-list');
  if (!root) return;

  let currentGroup = '';
  let currentInvStatus = '';
  let currentCatId = '';
  let currentShopOnly = false;
  let invItems = [];
  let dragItemId = null;

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  async function loadInventory() {
    let url = '/api/v2/inventory?';
    if (currentCatId) {
      const r = await fetch(`/api/v2/inventory/available?inventory_category_id=${currentCatId}`);
      invItems = await r.json();
    } else {
      if (currentShopOnly) url += 'shopping_list=true&';
      const res = await fetch(url);
      invItems = await res.json();
    }

    // Client-side group & status filter if needed
    if (currentGroup) {
      invItems = invItems.filter(i => (i.group_type || 'equipment') === currentGroup);
    }
    if (currentInvStatus) {
      invItems = invItems.filter(i => i.inventory_status === currentInvStatus);
    }

    renderInventory();
    updateCounter();
  }

  function updateCounter() {
    const totalEl = document.getElementById('inv-total');
    if (totalEl) {
      totalEl.textContent = `Всего в справочнике: ${invItems.length} позиций`;
    }
  }

  async function loadCategories() {
    try {
      const r = await fetch('/api/v2/inventory-categories');
      invCategories = await r.json();
      renderCatFilters();
    } catch (e) { /* no categories */ }
  }

  function renderCatFilters() {
    const container = document.getElementById('inv-cat-filters');
    if (!container) return;
    container.innerHTML = invCategories.map(c =>
      `<button onclick="filterByCat('${c.id}')" data-cat="${c.id}" class="filter-btn px-2.5 py-1 rounded-lg border border-[color:var(--border)] pl-surface-soft text-xs text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-soft)] font-medium transition-colors">${escapeHtml(c.title)}</button>`
    ).join('');
  }

  function filterByCat(catId) {
    currentCatId = currentCatId === catId ? '' : catId;
    currentGroup = '';
    currentShopOnly = false;
    loadInventory();
  }

  function filterGroup(group) {
    currentGroup = group;
    currentCatId = '';
    currentShopOnly = false;
    document.querySelectorAll('#group-type-tabs .group-btn').forEach(b => {
      b.classList.remove('active', 'border-[color:var(--accent)]', 'bg-[color:var(--surface-raised)]');
    });
    const activeBtn = document.querySelector(`[data-group="${group}"]`);
    if (activeBtn) activeBtn.classList.add('active', 'border-[color:var(--accent)]', 'bg-[color:var(--surface-raised)]');
    loadInventory();
  }

  function filterInvStatus(status) {
    currentInvStatus = currentInvStatus === status ? '' : status;
    loadInventory();
  }

  function filterShoppingList() {
    currentShopOnly = !currentShopOnly;
    currentGroup = '';
    currentCatId = '';
    loadInventory();
  }

  function renderInventory() {
    const el = document.getElementById('inv-list');

    el.innerHTML = invItems.map(i => {
      const groupTitle = GROUP_LABELS[i.group_type || 'equipment'] || i.group_type;
      const statusTitle = INV_STATUS_LABEL[i.inventory_status || 'available'] || i.inventory_status;
      const isServicedRecently = i.last_serviced_at ? true : false;
      const lastServicedDate = i.last_serviced_at ? new Date(i.last_serviced_at).toLocaleDateString('ru-RU') : 'не проводилась';

      return `
        <div class="pl-surface rounded-2xl border border-[color:var(--border)] p-4 hover:border-[color:var(--border-strong)] transition-all cursor-grab space-y-3" draggable="true" data-id="${escapeHtml(String(i.id))}">
          <div class="flex items-start gap-4">
            <span class="text-[color:var(--text-muted)] select-none pt-2 flex items-center">⠿</span>

            ${i.image_path ? `
              <img src="${escapeHtml(i.image_path)}" alt="" class="w-32 aspect-[4/3] rounded-xl object-cover flex-shrink-0 border border-[color:var(--border)]${window.__dscrBlurCls || ''}" loading="lazy">
            ` : `
              <div class="inv-img-placeholder w-32 aspect-[4/3] rounded-xl bg-[color:var(--surface-soft)] flex items-center justify-center text-[color:var(--text-muted)] flex-shrink-0 border border-[color:var(--border)]"></div>
            `}

            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap mb-1">
                <span class="text-xs px-2.5 py-0.5 rounded-full font-medium bg-[color:var(--surface-soft)] text-[color:var(--text-secondary)] border border-[color:var(--border)]">
                  ${escapeHtml(groupTitle)}
                </span>
                <span class="text-xs px-2.5 py-0.5 rounded-full font-medium ${invStatusBadge(i.inventory_status)}">
                  ${escapeHtml(statusTitle)}
                </span>
                ${i.is_shopping_list ? `<span class="text-xs bg-[color:var(--warning-soft)] text-[color:var(--warning)] px-2.5 py-0.5 rounded-full font-medium">🛒 Корзина закупок</span>` : ''}
              </div>

              <h3 class="text-base font-semibold text-[color:var(--text)]">${escapeHtml(i.name)}</h3>

              <!-- ERP Specifications Drawer -->
              <div class="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-[color:var(--text-secondary)]">
                ${i.category ? `<span>Категория: <strong class="text-[color:var(--text)]">${escapeHtml(i.category)}</strong></span>` : ''}
                ${i.manufacturer ? `<span>Бренд: <strong class="text-[color:var(--text)]">${escapeHtml(i.manufacturer)}</strong></span>` : ''}
                ${i.model_name ? `<span>Модель: <strong class="text-[color:var(--text)]">${escapeHtml(i.model_name)}</strong></span>` : ''}
                ${i.material ? `<span>Материал: <strong class="text-[color:var(--text)]">${escapeHtml(i.material)}</strong></span>` : ''}
                ${i.size_color ? `<span>Размер/Цвет: <strong class="text-[color:var(--text)]">${escapeHtml(i.size_color)}</strong></span>` : ''}
              </div>

              <div class="text-[11px] text-[color:var(--text-muted)] mt-2 flex items-center gap-3">
                <span>Количество: <strong>${i.quantity}/${i.quantity_needed} шт</strong></span>
                <span>ТО / Дезинфекция: <strong>${lastServicedDate}</strong></span>
                ${i.maintenance_interval_days ? `<span>Интервал ТО: <strong>${i.maintenance_interval_days} дн.</strong></span>` : ''}
              </div>
            </div>

            <!-- ERP Item Quick Action Toolbar -->
            <div class="flex items-center gap-2 flex-shrink-0 self-start">
              <button onclick="serviceItem('${escapeHtml(String(i.id))}')" class="px-2.5 py-1.5 rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-soft)] hover:bg-emerald-100 hover:text-emerald-700 text-xs font-medium transition-colors flex items-center gap-1" title="Отметить дезинфекцию / обслуживание сегодня">
                🧹 ТО / Очистить
              </button>
              <button onclick="pickImage('${escapeHtml(String(i.id))}')" class="p-1.5 rounded-lg border border-[color:var(--border)] pl-surface-soft hover:text-[color:var(--accent)] text-xs" title="Загрузить фото" aria-label="Photo"></button>
              ${i.image_path ? `<button onclick="delImage('${escapeHtml(String(i.id))}')" class="p-1.5 rounded-lg border border-[color:var(--border)] pl-surface-soft hover:text-[color:var(--danger)] text-xs" title="Удалить фото" aria-label="Remove photo"></button>` : ''}
              <button onclick="del('${escapeHtml(String(i.id))}')" class="p-1.5 rounded-lg border border-[color:var(--danger)] text-[color:var(--danger)] hover:bg-red-50 dark:hover:bg-red-900/30 text-xs font-medium">Удалить</button>
            </div>
          </div>
        </div>
      `;
    }).join('') || '<div class="text-center py-12 pl-surface rounded-2xl border border-[color:var(--border)] text-[color:var(--text-muted)]"><p class="text-sm font-medium">Справочник номенклатуры пуст.</p><p class="text-xs mt-1">Добавьте первую позицию с помощью кнопки вверху.</p></div>';

    // Inject SVG icons
    const rows = el.querySelectorAll('[data-id]');
    rows.forEach((row) => {
      const photoBtn = row.querySelector('button[aria-label="Photo"]');
      if (photoBtn && !photoBtn.querySelector('svg')) {
        photoBtn.appendChild(window.plIcon('camera', 'w-4 h-4'));
      }
      const delImgBtn = row.querySelector('button[aria-label="Remove photo"]');
      if (delImgBtn && !delImgBtn.querySelector('svg')) {
        delImgBtn.textContent = '';
        delImgBtn.appendChild(window.plIcon('close', 'w-4 h-4'));
      }
      const placeholder = row.querySelector('.inv-img-placeholder');
      if (placeholder && !placeholder.querySelector('svg')) {
        placeholder.appendChild(window.plIcon('image', 'w-6 h-6'));
      }
      const dragHandle = row.querySelector('span.select-none');
      if (dragHandle) {
        dragHandle.textContent = '';
        dragHandle.appendChild(window.plIcon('more', 'w-4 h-4'));
      }
    });
  }

  function invStatusBadge(s) {
    const m = {
      available: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
      in_use: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
      cleaning: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
      charging: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
      maintenance: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
      archived: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
      unavailable: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    };
    return m[s] || 'bg-[color:var(--surface-soft)] text-[color:var(--text-secondary)]';
  }

  // 1-Click Service Action
  async function serviceItem(id) {
    const res = await fetch(`/api/v2/inventory/${id}/service`, { method: 'POST' });
    if (res.ok) loadInventory();
  }

  function showForm() {
    document.getElementById('add-form').classList.remove('hidden');
  }

  function hideForm() {
    document.getElementById('add-form').classList.add('hidden');
  }

  async function del(id) {
    if (!confirm('Удалить эту позицию из номенклатуры?')) return;
    await fetch('/api/v2/inventory/' + id, { method: 'DELETE' });
    loadInventory();
  }

  // Handle Form Submit
  const invForm = document.getElementById('inv-form');
  if (invForm) {
    invForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = {
        group_type: document.getElementById('inv-group-type').value,
        category: document.getElementById('inv-cat').value || 'Разное',
        name: document.getElementById('inv-name').value,
        manufacturer: document.getElementById('inv-manufacturer').value || null,
        model_name: document.getElementById('inv-model-name').value || null,
        material: document.getElementById('inv-material').value || null,
        size_color: document.getElementById('inv-size-color').value || null,
        quantity: parseInt(document.getElementById('inv-qty').value, 10) || 1,
        quantity_needed: parseInt(document.getElementById('inv-qtyn').value, 10) || 1,
        inventory_status: document.getElementById('inv-operational-status').value,
        maintenance_interval_days: parseInt(document.getElementById('inv-maint-interval').value, 10) || null,
        priority: parseInt(document.getElementById('inv-prio').value, 10) || 0,
        is_shopping_list: document.getElementById('inv-shop').checked,
      };
      await fetch('/api/v2/inventory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      hideForm();
      invForm.reset();
      loadInventory();
    });
  }

  // Image Upload handlers
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
      if (res.ok) loadInventory();
    });
  }

  async function delImage(id) {
    await fetch('/api/v2/inventory/' + id + '/image', { method: 'DELETE' });
    loadInventory();
  }

  // Drag and Drop reordering
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
    list.addEventListener('dragover', (e) => e.preventDefault());
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
      loadInventory();
    });
  }

  bindDrag();
  loadInventory();
  loadCategories();

  // Global window functions for template buttons
  window.del = del;
  window.delImage = delImage;
  window.filterGroup = filterGroup;
  window.filterInvStatus = filterInvStatus;
  window.filterShoppingList = filterShoppingList;
  window.filterByCat = filterByCat;
  window.pickImage = pickImage;
  window.showForm = showForm;
  window.hideForm = hideForm;
  window.serviceItem = serviceItem;
})();
