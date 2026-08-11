// Tasks page: preference selectors, filter bar, manual creation form (ADR-041),
// quick actions + completion card (ADR-040). Extracted per DESIGN.md 15.4.
// i18n strings come from the <script type="application/json" id="page-i18n"> block.
(function () {
  'use strict';
  var T = {};
  try {
    var el = document.getElementById('page-i18n');
    if (el) T = JSON.parse(el.textContent) || {};
  } catch (e) { /* no i18n */ }
  var ANY = T.tasks_prefs_any || 'Any';

  // --- CSRF header (same-origin state-changing fetch) ---
  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  }

  // --- Reference data for selectors ---
  async function loadBodyParts(intoId, selectedId) {
    var sel = document.getElementById(intoId);
    if (!sel) return;
    try {
      var r = await fetch('/api/v2/body-parts');
      var items = await r.json();
      items.forEach(function (bp) {
        var opt = document.createElement('option');
        opt.value = bp.id;
        opt.textContent = bp.title + (bp.body_system ? ' (' + bp.body_system + ')' : '');
        if (bp.id === selectedId) opt.selected = true;
        sel.appendChild(opt);
      });
    } catch (e) { /* ignore */ }
  }

  async function loadLocations(intoId, selectedId) {
    var sel = document.getElementById(intoId);
    if (!sel) return;
    try {
      var r = await fetch('/api/v2/locations');
      var items = await r.json();
      items.forEach(function (loc) {
        var opt = document.createElement('option');
        opt.value = loc.id;
        opt.textContent = (loc.location_type ? '[' + loc.location_type + '] ' : '') + loc.title;
        if (loc.id === selectedId) opt.selected = true;
        sel.appendChild(opt);
      });
    } catch (e) { /* ignore */ }
  }

  async function loadInventoryItems(intoId, selectedId) {
    var sel = document.getElementById(intoId);
    if (!sel) return;
    try {
      var r = await fetch('/api/v2/inventory/available');
      var items = await r.json();
      items.forEach(function (item) {
        var opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = item.name;
        if (item.id === selectedId) opt.selected = true;
        sel.appendChild(opt);
      });
    } catch (e) { /* ignore */ }
  }

  // Populate every <select data-selector="..."> inside a container
  function initSelectorFields(container) {
    if (!container) return;
    var sels = container.querySelectorAll('select[data-selector]');
    sels.forEach(function (sel) {
      var type = sel.getAttribute('data-selector');
      if (type === 'body_part_selector') loadBodyParts(sel.id, '');
      else if (type === 'location_selector') loadLocations(sel.id, '');
      else if (type === 'inventory_selector') loadInventoryItems(sel.id, '');
    });
  }

  // --- Manual creation form ---
  var manualSelect = document.getElementById('manual-entity');
  var manualParams = document.getElementById('manual-params');

  if (manualSelect && manualParams) {
    manualSelect.addEventListener('change', async function () {
      var eid = manualSelect.value;
      manualParams.classList.remove('hidden');
      manualParams.innerHTML = '<div class="flex items-center gap-2 text-sm text-slate-400">' +
        '<span class="animate-pulse">●</span> ' + (T.tasks_manual_loading || 'Loading…') + '</div>';
      var errBox = document.getElementById('manual-params-error');
      if (errBox) errBox.classList.add('hidden');
      if (!eid) { manualParams.classList.add('hidden'); manualParams.innerHTML = ''; return; }
      try {
        var r = await fetch('/tasks/params-form?entity_id=' + encodeURIComponent(eid) + '&prefix=param_');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        var html = await r.text();
        manualParams.innerHTML =
          '<form id="manual-create-form" action="/tasks/create" method="post" class="space-y-3">' +
          '<input type="hidden" name="csrf_token" value="' + csrfToken() + '">' +
          '<input type="hidden" name="entity_id" value="' + eid + '">' +
          '<div class="max-h-72 overflow-y-auto pr-1">' + html + '</div>' +
          '<div>' +
          '  <label for="manual-comment" class="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">' +
          (T.tasks_manual_comment || 'Planned comment') + '</label>' +
          '  <input id="manual-comment" name="planned_comment" placeholder="' + (T.tasks_manual_comment_ph || '') + '"' +
          '    class="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">' +
          '</div>' +
          '<button type="submit" class="px-4 py-2 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium min-h-[44px]">' +
          (T.tasks_manual_create_btn || 'Create task') + '</button>' +
          '</form>';
        initSelectorFields(manualParams);
      } catch (e) {
        manualParams.innerHTML = '';
        if (errBox) {
          errBox.textContent = (T.tasks_manual_errors || 'Failed to load parameters') + ' (' + e.message + ')';
          errBox.classList.remove('hidden');
        }
      }
    });
  }

  // --- Quick actions (status machine, ADR-040) ---
  function postTransition(taskId, toStatus, payload) {
    var body = Object.assign({ to_status: toStatus }, payload || {});
    return fetch('/api/v2/tasks/' + encodeURIComponent(taskId) + '/transition', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
      body: JSON.stringify(body),
    });
  }

  document.addEventListener('click', async function (ev) {
    var btn = ev.target.closest('.task-action-btn');
    if (btn) {
      ev.preventDefault();
      var taskId = btn.getAttribute('data-transition');
      var toStatus = btn.getAttribute('data-to-status');

      // Completing / partial → open the completion card instead of instant transition
      if (toStatus === 'completed' || toStatus === 'partially_completed') {
        openCompletionCard(taskId, toStatus);
        return;
      }
      btn.disabled = true;
      try {
        await postTransition(taskId, toStatus, {});
        window.location.reload();
      } catch (e) {
        btn.disabled = false;
        alert('Transition failed: ' + e.message);
      }
      return;
    }

    // Completion card submit
    var doneBtn = ev.target.closest('[data-complete]');
    if (doneBtn) {
      ev.preventDefault();
      var cTaskId = doneBtn.getAttribute('data-complete');
      var cToStatus = doneBtn.getAttribute('data-to-status');
      var card = document.getElementById('complete-card-' + cTaskId);
      var fields = card ? card.querySelectorAll('[name^="actual_"]') : [];
      var actual = {};
      fields.forEach(function (f) {
        var name = f.getAttribute('name').slice('actual_'.length);
        if (f.type === 'checkbox') {
          if (f.checked) actual[name] = true;
        } else if (f.value !== '') {
          actual[name] = f.value;
        }
      });
      var commentEl = document.getElementById('completion-comment-' + cTaskId);
      var comment = commentEl ? commentEl.value : '';
      doneBtn.disabled = true;
      try {
        await postTransition(cTaskId, cToStatus, {
          actual_parameters: Object.keys(actual).length ? actual : null,
          comment: comment || null,
        });
        window.location.reload();
      } catch (e) {
        doneBtn.disabled = false;
        alert('Save failed: ' + e.message);
      }
      return;
    }

    // Cancel completion card
    var cancelBtn = ev.target.closest('.complete-card-cancel');
    if (cancelBtn) {
      var cardId = cancelBtn.getAttribute('data-card');
      var c = document.getElementById('complete-card-' + cardId);
      if (c) c.classList.add('hidden');
    }
  });

  // Open the completion card and lazy-load actual-params fields from the DSL schema
  function openCompletionCard(taskId, toStatus) {
    var card = document.getElementById('complete-card-' + taskId);
    if (!card) return;
    card.classList.remove('hidden');
    card.querySelector('[data-complete]').setAttribute('data-to-status', toStatus);
    var fieldsBox = document.getElementById('actual-fields-' + taskId);
    if (fieldsBox && !fieldsBox.dataset.loaded) {
      fieldsBox.dataset.loaded = '1';
      var eid = fieldsBox.getAttribute('data-entity-id');
      var prefix = fieldsBox.getAttribute('data-prefix') || 'actual_';
      fetch('/tasks/params-form?entity_id=' + encodeURIComponent(eid) + '&prefix=' + encodeURIComponent(prefix))
        .then(function (r) { return r.ok ? r.text() : Promise.reject(new Error('HTTP ' + r.status)); })
        .then(function (html) {
          fieldsBox.innerHTML = html;
          initSelectorFields(fieldsBox);
        })
        .catch(function () {
          fieldsBox.innerHTML = '<div class="text-sm text-slate-400">' + (T.tasks_complete_actual_empty || 'No parameters') + '</div>';
        });
    }
  }

  // --- Preference selects (form) ---
  loadBodyParts('pref-body-part', '');
  loadLocations('pref-location', '');
  loadInventoryItems('pref-item', '');

  // Load filter selects (history) — with current selections from data attrs
  var filterBar = document.getElementById('filter-bar');
  var selBp = filterBar ? filterBar.dataset.bodyPartId || '' : '';
  var selLoc = filterBar ? filterBar.dataset.locationId || '' : '';
  var selInv = filterBar ? (filterBar.dataset.inventoryItemId || '') : '';

  loadBodyParts('filter-body-part', selBp);
  loadLocations('filter-location', selLoc);
  loadInventoryItems('filter-inventory', selInv);

  // --- Filter navigation ---
  window.applyFilter = function () {
    var params = new URLSearchParams();
    var status = document.getElementById('filter-status');
    if (status && status.value && status.value !== 'all') params.set('status', status.value);
    var bp = document.getElementById('filter-body-part');
    if (bp && bp.value) params.set('body_part_id', bp.value);
    var loc = document.getElementById('filter-location');
    if (loc && loc.value) params.set('location_id', loc.value);
    var inv = document.getElementById('filter-inventory');
    if (inv && inv.value) params.set('inventory_item_id', inv.value);
    var qs = params.toString();
    window.location.href = '/tasks/' + (qs ? '?' + qs : '');
  };
})();
