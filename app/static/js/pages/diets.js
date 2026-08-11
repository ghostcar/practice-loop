// Diets page: CRUD, items DnD, photos, consumption journal, AI generate/evaluate,
// evaluation history, diet↔training synergy (extracted from diets.html, DESIGN.md 15.4).
// i18n + HAS_LLM + initial diets come from the <script type="application/json" id="page-i18n"> block.
(function () {
  'use strict';
  let P = {};
  try {
    const el = document.getElementById('page-i18n');
    if (el) P = JSON.parse(el.textContent) || {};
  } catch (e) {
    console.warn('Diets page data:', e);
  }
  const I18N = P.i18n || {};
  const HAS_LLM = !!P.has_llm;

  let diets = Array.isArray(P.diets) ? P.diets : [];
  let dragItemId = null;

  const root = document.getElementById('diets-list');
  if (!root) return;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function qtyStr(it) {
    if (it.quantity == null) return '';
    const q = Number(it.quantity);
    const num = Number.isInteger(q) ? String(q) : q.toFixed(1).replace(/\.0$/, '');
    return it.unit ? num + ' ' + it.unit : num;
  }

  function renderDiets() {
    const list = document.getElementById('diets-list');
    list.innerHTML = '';
    diets.forEach((d) => list.appendChild(renderDietCard(d)));
    // Combined hint when several diets active
    const active = diets.filter((d) => d.is_active);
    const hint = document.getElementById('combined-hint');
    if (active.length > 1) {
      if (!hint) {
        const h = el('div', 'p-3 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-lg text-sm text-emerald-700 dark:text-emerald-300');
        h.id = 'combined-hint';
        h.textContent = I18N.combined + ': ' + active.map((d) => d.name).join(' + ');
        list.prepend(h);
      } else {
        hint.textContent = I18N.combined + ': ' + active.map((d) => d.name).join(' + ');
      }
    } else if (hint) {
      hint.remove();
    }
  }

  function renderDietCard(d) {
    const card = el('div', 'bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden' + (d.is_active ? ' border-emerald-300 dark:border-emerald-700' : ''));

    // Header
    const head = el('div', 'flex items-start justify-between gap-3 p-4 border-b border-slate-100 dark:border-slate-800');
    const left = el('div', 'flex-1 min-w-0');
    const titleRow = el('div', 'flex items-center gap-2 flex-wrap');
    titleRow.appendChild(el('h3', 'font-semibold text-slate-800 dark:text-slate-100', d.name));
    if (d.is_active) titleRow.appendChild(el('span', 'text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300', I18N.active));
    left.appendChild(titleRow);
    if (d.goal) left.appendChild(el('p', 'text-xs text-slate-500 dark:text-slate-400 mt-1', I18N.goal + ': ' + d.goal));
    if (d.direction) left.appendChild(el('span', 'text-xs px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 mt-1 inline-block', d.direction));
    if (d.description) left.appendChild(el('p', 'text-xs text-slate-400 dark:text-slate-500 mt-0.5', d.description));
    head.appendChild(left);

    const actions = el('div', 'flex items-center gap-2 flex-shrink-0 flex-wrap');
    const histBtn = el('button', 'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors min-h-[44px] bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-fuchsia-400');
    histBtn.textContent = I18N.eval_history_btn;
    histBtn.title = I18N.eval_history;
    histBtn.onclick = () => showHistory(d.id, card);
    actions.appendChild(histBtn);
    if (HAS_LLM) {
      const evalBtn = el('button', 'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors min-h-[44px] bg-gradient-to-r from-fuchsia-500 to-indigo-500 hover:from-fuchsia-600 hover:to-indigo-600 text-white');
      evalBtn.textContent = '🤖';
      evalBtn.title = I18N.evaluate_btn;
      evalBtn.onclick = () => evaluateDiet(d.id);
      actions.appendChild(evalBtn);
    }
    const activeBtn = el('button', 'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors min-h-[44px] border ' + (d.is_active ? 'bg-emerald-600 hover:bg-emerald-700 text-white border-emerald-600' : 'bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-emerald-400'));
    activeBtn.textContent = d.is_active ? I18N.active : I18N.inactive;
    activeBtn.title = I18N.active;
    activeBtn.onclick = () => toggleDiet(d.id, !d.is_active);
    actions.appendChild(activeBtn);

    const editBtn = el('button', 'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors min-h-[44px] bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-indigo-400', I18N.edit);
    editBtn.onclick = () => editDiet(d);
    actions.appendChild(editBtn);

    const delBtn = el('button', 'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors min-h-[44px] bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-red-500 hover:border-red-400', I18N.delete);
    delBtn.onclick = () => deleteDiet(d.id);
    actions.appendChild(delBtn);
    head.appendChild(actions);
    card.appendChild(head);

    // Photos (attachments on owner_type=diet)
    const body = el('div', 'p-4');
    const photosWrap = el('div', 'flex flex-wrap items-center gap-2 mb-3');
    photosWrap.dataset.dietPhotos = d.id;
    const photoBtn = el('label', 'px-3 py-1.5 rounded-lg text-xs font-medium min-h-[44px] cursor-pointer bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-indigo-400 inline-flex items-center gap-1');
    photoBtn.textContent = '📷 ' + I18N.photo_add;
    const photoInput = el('input', 'hidden');
    photoInput.type = 'file';
    photoInput.accept = 'image/*';
    photoInput.onchange = async () => {
      if (!photoInput.files.length) return;
      const fd = new FormData();
      fd.append('file', photoInput.files[0]);
      fd.append('owner_type', 'diet');
      fd.append('owner_id', d.id);
      await fetch('/attachments', { method: 'POST', body: fd });
      await loadDietPhotos(d.id);
    };
    photoBtn.appendChild(photoInput);
    photosWrap.appendChild(photoBtn);
    body.appendChild(photosWrap);

    // Items
    const itemsWrap = el('div', 'space-y-1.5');
    itemsWrap.dataset.dietId = d.id;
    if (d.items && d.items.length) {
      d.items.forEach((it) => itemsWrap.appendChild(renderItemRow(d.id, it)));
    } else {
      itemsWrap.appendChild(el('p', 'text-xs text-slate-400 dark:text-slate-500 py-2', I18N.no_items));
    }
    body.appendChild(itemsWrap);

    // Evaluation block (if the LLM already evaluated this diet)
    if (d.last_evaluation && d.last_evaluation.score !== undefined) {
      const ev = d.last_evaluation;
      const evBlock = el('div', 'mt-3 p-3 rounded-lg bg-fuchsia-50 dark:bg-fuchsia-950/20 border border-fuchsia-200 dark:border-fuchsia-800/50');
      const evHead = el('div', 'flex items-center gap-3 mb-1');
      evHead.appendChild(el('span', 'text-xs font-semibold text-fuchsia-700 dark:text-fuchsia-300', I18N.eval_title));
      const scoreColor = ev.score >= 70 ? 'text-emerald-600 dark:text-emerald-400' : ev.score >= 40 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';
      evHead.appendChild(el('span', 'text-sm font-bold ' + scoreColor, I18N.eval_score + ': ' + Math.round(ev.score) + '/100'));
      evBlock.appendChild(evHead);
      evBlock.appendChild(el('p', 'text-xs text-slate-600 dark:text-slate-300', ev.summary || ''));
      if (ev.findings && ev.findings.length) {
        evBlock.appendChild(el('p', 'text-xs font-semibold text-slate-500 dark:text-slate-400 mt-2', I18N.eval_findings + ':'));
        ev.findings.forEach((f) => evBlock.appendChild(el('li', 'text-xs text-slate-500 dark:text-slate-400 ml-4 list-disc', f)));
      }
      if (ev.applied && ev.applied.length) {
        evBlock.appendChild(el('p', 'text-xs text-emerald-600 dark:text-emerald-400 mt-2', I18N.eval_applied + ' (' + ev.applied.length + ')'));
      }
      body.appendChild(evBlock);
    }

    const addForm = el('form', 'mt-3 flex flex-wrap gap-2 items-center');
    const iName = el('input', 'flex-1 min-w-[140px] px-2.5 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-100');
    iName.placeholder = I18N.ph_item;
    iName.required = true;
    const iQty = el('input', 'w-16 px-2 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-100');
    iQty.placeholder = I18N.ph_qty;
    iQty.type = 'number';
    iQty.step = 'any';
    const iUnit = el('input', 'w-16 px-2 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-100');
    iUnit.placeholder = I18N.ph_unit;
    iUnit.maxLength = 20;
    const iMeal = el('input', 'w-20 px-2 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-100');
    iMeal.placeholder = I18N.ph_meal;
    iMeal.maxLength = 30;
    const iNotes = el('input', 'flex-1 min-w-[120px] px-2 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-100');
    iNotes.placeholder = I18N.ph_notes;
    iNotes.maxLength = 2000;
    const iBtn = el('button', 'px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-lg min-h-[44px]', I18N.add_item);
    iBtn.type = 'submit';
    [iName, iQty, iUnit, iMeal, iNotes, iBtn].forEach((c) => addForm.appendChild(c));
    addForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await addItem(d.id, {
        name: iName.value.trim(),
        quantity: iQty.value === '' ? null : parseFloat(iQty.value),
        unit: iUnit.value.trim() || null,
        meal_time: iMeal.value.trim() || null,
        notes: iNotes.value.trim() || null,
      });
      iName.value = '';
      iQty.value = '';
      iUnit.value = '';
      iMeal.value = '';
      iNotes.value = '';
    });
    body.appendChild(addForm);
    card.appendChild(body);
    return card;
  }

  function renderItemRow(dietId, it) {
    const row = el('div', 'flex items-center gap-2 p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/40 cursor-grab drag-item');
    row.draggable = true;
    row.dataset.id = it.id;
    const grip = el('span', 'text-slate-300 dark:text-slate-600 select-none', '⠿');
    const name = el('span', 'flex-1 text-sm text-slate-700 dark:text-slate-300 min-w-0 truncate cursor-pointer hover:text-indigo-600 dark:hover:text-indigo-400', it.name);
    name.title = I18N.item_edit;
    const meta = el('span', 'text-xs text-slate-400 flex-shrink-0');
    meta.textContent = [qtyStr(it), it.meal_time].filter(Boolean).join(' · ');
    const editBtn = el('button', 'text-slate-400 hover:text-indigo-600 text-xs px-1 min-h-[44px]', '✎');
    editBtn.title = I18N.item_edit;
    const del = el('button', 'text-red-400 hover:text-red-600 text-xs px-1 min-h-[44px]', '✕');
    del.onclick = () => deleteItem(dietId, it.id);
    editBtn.onclick = () => editItemInline(dietId, it);
    name.onclick = () => editItemInline(dietId, it);
    [grip, name, meta, editBtn, del].forEach((c) => row.appendChild(c));

    row.addEventListener('dragstart', (e) => {
      dragItemId = it.id;
      row.classList.add('opacity-50');
      e.dataTransfer.effectAllowed = 'move';
    });
    row.addEventListener('dragend', () => {
      row.classList.remove('opacity-50');
      dragItemId = null;
    });
    row.addEventListener('dragover', (e) => {
      e.preventDefault();
    });
    row.addEventListener('drop', (e) => {
      e.preventDefault();
      if (!dragItemId || dragItemId === it.id) return;
      const wrap = row.parentElement;
      const ids = Array.from(wrap.querySelectorAll('.drag-item')).map((r) => r.dataset.id);
      const from = ids.indexOf(dragItemId);
      const to = ids.indexOf(it.id);
      if (from < 0 || to < 0) return;
      ids.splice(from, 1);
      ids.splice(to, 0, dragItemId);
      reorderItems(dietId, ids);
    });
    return row;
  }

  function editItemInline(dietId, it) {
    const wrap = document.querySelector('#diets-list [data-diet-id="' + dietId + '"]');
    const row = wrap && wrap.querySelector('[data-id="' + it.id + '"]');
    if (!row) return;
    const form = document.createElement('form');
    form.className = 'flex flex-wrap items-center gap-2 p-2 rounded-lg border border-indigo-300 dark:border-indigo-700 bg-indigo-50/50 dark:bg-indigo-950/20';
    const fName = el('input', 'flex-1 min-w-[120px] px-2 py-1.5 text-xs bg-white dark:bg-slate-800 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-100');
    fName.value = it.name;
    fName.maxLength = 300;
    fName.required = true;
    const fQty = el('input', 'w-16 px-2 py-1.5 text-xs bg-white dark:bg-slate-800 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-100');
    fQty.type = 'number';
    fQty.step = 'any';
    fQty.placeholder = I18N.ph_qty;
    fQty.value = it.quantity == null ? '' : it.quantity;
    const fUnit = el('input', 'w-16 px-2 py-1.5 text-xs bg-white dark:bg-slate-800 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-100');
    fUnit.placeholder = I18N.ph_unit;
    fUnit.maxLength = 20;
    fUnit.value = it.unit || '';
    const fMeal = el('input', 'w-20 px-2 py-1.5 text-xs bg-white dark:bg-slate-800 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-100');
    fMeal.placeholder = I18N.ph_meal;
    fMeal.maxLength = 30;
    fMeal.value = it.meal_time || '';
    const fNotes = el('input', 'flex-1 min-w-[120px] px-2 py-1.5 text-xs bg-white dark:bg-slate-800 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-100');
    fNotes.placeholder = I18N.ph_notes;
    fNotes.maxLength = 2000;
    fNotes.value = it.notes || '';
    const fBtn = el('button', 'px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-lg min-h-[44px]', I18N.save_item);
    fBtn.type = 'submit';
    const fCancel = el('button', 'px-3 py-1.5 text-xs font-medium rounded-lg min-h-[44px] bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300', '✕');
    fCancel.type = 'button';
    fCancel.onclick = () => {
      row.replaceWith(renderItemRow(dietId, it));
    };
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      await api('/diets/api/' + dietId + '/items/' + it.id, 'PUT', {
        name: fName.value.trim(),
        quantity: fQty.value === '' ? null : parseFloat(fQty.value),
        unit: fUnit.value.trim() || null,
        meal_time: fMeal.value.trim() || null,
        notes: fNotes.value.trim() || null,
      });
      await reloadDiets();
    });
    [fName, fQty, fUnit, fMeal, fNotes, fBtn, fCancel].forEach((c) => form.appendChild(c));
    row.replaceWith(form);
  }

  // ── API calls ──

  async function api(url, method, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Request failed');
    }
    return res.status === 204 ? null : res.json();
  }

  async function toggleDiet(id, active) {
    await api('/diets/api/' + id, 'PUT', { is_active: active });
    const d = diets.find((x) => x.id === id);
    if (d) d.is_active = active;
    renderDiets();
  }

  async function deleteDiet(id) {
    if (!confirm(I18N.delete + '?')) return;
    await api('/diets/api/' + id, 'DELETE');
    diets = diets.filter((x) => x.id !== id);
    renderDiets();
  }

  function editDiet(d) {
    document.getElementById('diet-form').classList.remove('hidden');
    document.getElementById('diet-name').value = d.name;
    document.getElementById('diet-direction').value = d.direction || '';
    document.getElementById('diet-goal').value = d.goal || '';
    document.getElementById('diet-desc').value = d.description || '';
    document.getElementById('diet-active').checked = d.is_active;
    document.getElementById('diet-form-fields').dataset.editingId = d.id;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function addItem(dietId, data) {
    await api('/diets/api/' + dietId + '/items', 'POST', data);
    await reloadDiets();
  }

  async function deleteItem(dietId, itemId) {
    await api('/diets/api/' + dietId + '/items/' + itemId, 'DELETE');
    await reloadDiets();
  }

  async function reorderItems(dietId, ids) {
    await api('/diets/api/' + dietId + '/items/reorder', 'POST', { ids });
    await reloadDiets();
  }

  async function reloadDiets() {
    const res = await fetch('/diets/api');
    diets = await res.json();
    renderDiets();
    diets.forEach((d) => loadDietPhotos(d.id));
  }

  // ── AI generation ──

  function showGenForm() {
    const f = document.getElementById('gen-form');
    f.classList.toggle('hidden');
    document.getElementById('gen-error').classList.add('hidden');
    if (!f.classList.contains('hidden')) document.getElementById('gen-goal').focus();
  }

  async function generateDiet() {
    const btn = document.getElementById('gen-btn');
    const err = document.getElementById('gen-error');
    btn.disabled = true;
    err.classList.add('hidden');
    try {
      const goal = document.getElementById('gen-goal').value.trim();
      const body = {};
      // Heuristic: try to pick a direction from the goal text
      const dirMatch =
        (goal.match(/loss|weight|fat|худ|похуд|вес/i) && 'weight_loss') ||
        (goal.match(/muscle|bulk|gain|mass|набор|масс|мышц/i) && 'muscle_gain') ||
        (goal.match(/energy|энерг|бодр/i) && 'energy') ||
        (goal.match(/endur|stamina|выносл/i) && 'endurance') ||
        (goal.match(/health|здоров/i) && 'health') ||
        null;
      if (dirMatch) body.direction = dirMatch;
      if (goal) body.goal = goal;
      const diet = await api('/diets/api/generate', 'POST', body);
      await reloadDiets();
      document.getElementById('gen-form').classList.add('hidden');
      document.getElementById('gen-goal').value = '';
      editDiet(diet);
    } catch (e) {
      err.textContent = e.message;
      err.classList.remove('hidden');
    } finally {
      btn.disabled = false;
    }
  }

  async function evaluateDiet(dietId) {
    const d = diets.find((x) => x.id === dietId);
    if (!d) return;
    try {
      await api('/diets/api/' + dietId + '/evaluate', 'POST', { days: 7 });
      await reloadDiets();
    } catch (e) {
      alert(e.message);
    }
  }

  // ── Consumption journal ──

  async function loadConsumptions() {
    const res = await fetch('/diets/api/consumptions?consumed_date=' + new Date().toISOString().slice(0, 10));
    const items = await res.json();
    const wrap = document.getElementById('consumptions');
    wrap.innerHTML = '';
    if (!items.length) {
      wrap.appendChild(el('p', 'text-xs text-slate-400 dark:text-slate-500', I18N.consumed + ': —'));
      return;
    }
    wrap.appendChild(el('p', 'text-xs font-semibold text-slate-500 dark:text-slate-400', I18N.consumed + ' (' + items.length + '):'));
    items.forEach((c) => {
      const row = el('div', 'flex items-center gap-2 p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/40');
      const name = el('span', 'flex-1 text-sm text-slate-700 dark:text-slate-300 min-w-0 truncate', c.name);
      const meta = el('span', 'text-xs text-slate-400 flex-shrink-0');
      meta.textContent = [qtyStr(c), c.meal_time].filter(Boolean).join(' · ');
      const del = el('button', 'text-red-400 hover:text-red-600 text-xs px-1 min-h-[44px]', '✕');
      del.onclick = async () => {
        await api('/diets/api/consumptions/' + c.id, 'DELETE');
        await loadConsumptions();
      };
      [name, meta, del].forEach((x) => row.appendChild(x));
      wrap.appendChild(row);
    });
  }

  // ── Diet photos ──

  async function loadDietPhotos(dietId) {
    const wrap = document.querySelector('#diets-list [data-diet-photos="' + dietId + '"]');
    if (!wrap) return;
    // Remove old thumbnails (keep the upload button)
    Array.from(wrap.querySelectorAll('[data-photo]')).forEach((x) => x.remove());
    const res = await fetch('/attachments?owner_type=diet&owner_id=' + dietId);
    const atts = await res.json();
    atts.forEach((a) => {
      const imgWrap = el('div', 'relative group');
      imgWrap.dataset.photo = a.id;
      const img = el('img', 'w-14 h-14 object-cover rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer');
      img.src = a.file_path;
      img.onclick = () => window.open(a.file_path, '_blank');
      const delBtn = el('button', 'absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-red-500 text-white text-xs leading-none opacity-0 group-hover:opacity-100 transition-opacity', '✕');
      delBtn.title = I18N.photo_delete;
      delBtn.onclick = async () => {
        await api('/attachments/' + a.id, 'DELETE');
        await loadDietPhotos(dietId);
      };
      imgWrap.appendChild(img);
      imgWrap.appendChild(delBtn);
      wrap.appendChild(imgWrap);
    });
  }

  // ── Evaluation history ──

  async function showHistory(dietId, card) {
    const d = diets.find((x) => x.id === dietId);
    if (!d) return;
    const res = await fetch('/diets/api/' + dietId + '/evaluations');
    const evals = await res.json();
    const body = el('div', 'mt-3 p-3 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700');
    body.appendChild(el('p', 'text-xs font-semibold text-slate-600 dark:text-slate-300 mb-2', I18N.eval_history + ' — ' + d.name));
    if (!evals.length) {
      body.appendChild(el('p', 'text-xs text-slate-400', I18N.eval_history_empty));
    } else {
      evals.forEach((ev) => {
        const item = el('div', 'border-t border-slate-100 dark:border-slate-700 pt-2 mt-2 first:border-t-0 first:pt-0 first:mt-0');
        const headRow = el('div', 'flex items-center gap-2');
        const scoreColor = ev.score >= 70 ? 'text-emerald-600 dark:text-emerald-400' : ev.score >= 40 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';
        headRow.appendChild(el('span', 'text-sm font-bold ' + scoreColor, Math.round(ev.score) + '/100'));
        if (ev.created_at) headRow.appendChild(el('span', 'text-xs text-slate-400', new Date(ev.created_at).toLocaleDateString()));
        item.appendChild(headRow);
        item.appendChild(el('p', 'text-xs text-slate-500 dark:text-slate-400 mt-1', ev.summary || ''));
        body.appendChild(item);
      });
    }
    const closeBtn = el('button', 'mt-3 text-xs text-slate-400 hover:text-slate-600', '✕ close');
    closeBtn.onclick = () => body.remove();
    body.appendChild(closeBtn);
    if (card) card.appendChild(body);
  }

  // ── Diet ↔ Training synergy ──

  async function loadSynergyReviews() {
    const wrap = document.getElementById('synergy-reviews');
    const res = await fetch('/diets/api/synergy');
    const reviews = await res.json();
    wrap.innerHTML = '';
    if (!reviews.length) {
      wrap.appendChild(el('p', 'text-xs text-slate-400 dark:text-slate-500', I18N.synergy_empty));
      return;
    }
    reviews.forEach((r) => renderSynergyReview(wrap, r));
  }

  function renderSynergyReview(wrap, r) {
    const a = r.analysis || {};
    const block = el('div', 'p-3 rounded-lg bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/60');
    const head = el('div', 'flex items-center gap-2 mb-1 flex-wrap');
    head.appendChild(el('span', 'text-xs font-semibold text-amber-700 dark:text-amber-300', I18N.synergy_period + ': ' + r.period_start + ' — ' + r.period_end));
    if (r.created_at) head.appendChild(el('span', 'text-xs text-slate-400', new Date(r.created_at).toLocaleDateString()));
    block.appendChild(head);
    block.appendChild(el('p', 'text-sm text-slate-700 dark:text-slate-200', a.summary || ''));
    if (a.correlations && a.correlations.length) {
      block.appendChild(el('p', 'text-xs font-semibold text-slate-600 dark:text-slate-300 mt-2', I18N.synergy_correlations + ':'));
      a.correlations.forEach((c) => {
        const dirLabel = c.direction === 'training_to_diet' ? I18N.synergy_t2d : I18N.synergy_d2t;
        block.appendChild(el('li', 'text-xs text-slate-600 dark:text-slate-300 ml-4 list-disc', '[' + dirLabel + '] ' + c.text));
      });
    }
    if (a.adjustments && a.adjustments.length) {
      block.appendChild(el('p', 'text-xs font-semibold text-slate-600 dark:text-slate-300 mt-2', I18N.synergy_adjustments + ':'));
      a.adjustments.forEach((adj) => block.appendChild(el('li', 'text-xs text-slate-600 dark:text-slate-300 ml-4 list-disc', adj)));
    }
    wrap.appendChild(block);
  }

  async function runSynergy() {
    const btn = document.getElementById('synergy-btn');
    if (!btn) return;
    const orig = btn.textContent;
    btn.disabled = true;
    btn.textContent = '…';
    try {
      await api('/diets/api/synergy', 'POST', { days: 7 });
      await loadSynergyReviews();
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
    }
  }

  const consumeForm = document.getElementById('consume-form');
  if (consumeForm) {
    consumeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('consume-name').value.trim();
      if (!name) return;
      await api('/diets/api/consumptions', 'POST', {
        name,
        quantity: document.getElementById('consume-qty').value === '' ? null : parseFloat(document.getElementById('consume-qty').value),
        unit: document.getElementById('consume-unit').value.trim() || null,
        meal_time: document.getElementById('consume-meal').value.trim() || null,
        consumed_date: new Date().toISOString().slice(0, 10),
      });
      ['consume-name', 'consume-qty', 'consume-unit', 'consume-meal'].forEach((id) => (document.getElementById(id).value = ''));
      await loadConsumptions();
    });
  }

  // ── Init ──

  function showDietForm() {
    const f = document.getElementById('diet-form');
    f.classList.toggle('hidden');
    if (!f.classList.contains('hidden')) {
      document.getElementById('diet-form-fields').dataset.editingId = '';
      document.getElementById('diet-name').value = '';
      document.getElementById('diet-direction').value = '';
      document.getElementById('diet-goal').value = '';
      document.getElementById('diet-desc').value = '';
      document.getElementById('diet-active').checked = false;
      document.getElementById('diet-name').focus();
    }
  }

  const dietFieldsForm = document.getElementById('diet-form-fields');
  if (dietFieldsForm) {
    dietFieldsForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fields = e.target;
      const editingId = fields.dataset.editingId || '';
      const body = {
        name: document.getElementById('diet-name').value.trim(),
        direction: document.getElementById('diet-direction').value || null,
        goal: document.getElementById('diet-goal').value.trim() || null,
        description: document.getElementById('diet-desc').value.trim() || null,
        is_active: document.getElementById('diet-active').checked,
      };
      if (editingId) {
        await api('/diets/api/' + editingId, 'PUT', body);
      } else {
        await api('/diets/api', 'POST', body);
      }
      document.getElementById('diet-form').classList.add('hidden');
      await reloadDiets();
    });
  }

  // Fetch full list including items + today's consumptions + synergy + photos
  (async () => {
    const res = await fetch('/diets/api');
    diets = await res.json();
    renderDiets();
    await loadConsumptions();
    await loadSynergyReviews();
    diets.forEach((d) => loadDietPhotos(d.id));
  })();

  // Exposed for inline onclick handlers in the template.
  window.generateDiet = generateDiet;
  window.runSynergy = runSynergy;
  window.showDietForm = showDietForm;
  window.showGenForm = showGenForm;
})();
