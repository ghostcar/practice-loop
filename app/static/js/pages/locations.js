// Locations catalog page: list, CRUD, search, filter (DESIGN.md 15.4).
(function () {
  'use strict';

  var listEl = document.getElementById('loc-list');
  if (!listEl) return;

  var _editingId = null;

  (async function () {
    try {
      var r = await fetch('/api/v2/locations');
      window._locs = await r.json();
      renderList();
    } catch (e) {
      listEl.innerHTML = '<div class="p-4 text-sm text-red-700 dark:text-red-400">Failed to load locations</div>';
    }
  })();

  window.renderList = function () {
    var q = (document.getElementById('loc-search').value || '').toLowerCase();
    var tf = document.getElementById('loc-type-filter').value;
    var items = window._locs || [];
    if (tf) items = items.filter(function (l) { return l.location_type === tf; });
    if (q) {
      items = items.filter(function (l) {
        return (l.title || '').toLowerCase().indexOf(q) !== -1 ||
               (l.slug || '').toLowerCase().indexOf(q) !== -1;
      });
    }
    listEl.innerHTML = items.map(rowHTML).join('') ||
      '<div class="p-4 text-sm text-[color:var(--text-muted)]">No locations found</div>';
  };

  function rowHTML(loc) {
    var badge = loc.is_custom
      ? '<span class="text-xs px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 font-medium">Custom</span>'
      : '<span class="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500">System</span>';
    var icons = loc.is_custom
      ? '<button onclick="window._locEdit(\'' + loc.id + '\')\" class="text-[color:var(--text-muted)] hover:text-indigo-500 dark:hover:text-indigo-400 p-1">\u270e</button>' +
        '<button onclick="window._locArchive(\'' + loc.id + '\')\" class="text-[color:var(--text-muted)] hover:text-amber-500 p-1">\ud83d\udce6</button>' +
        '<button onclick="window._locDelete(\'' + loc.id + '\')\" class="text-[color:var(--text-muted)] hover:text-red-500 p-1">\u2715</button>'
      : '';
    return '<div class="flex items-center gap-3 px-4 py-2.5 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 transition-colors">' +
      '<span class="text-sm font-medium text-slate-700 dark:text-slate-200 flex-1">' + escHtml(loc.title) + '</span>' +
      '<span class="text-xs px-1.5 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500">' + escHtml(loc.location_type || '') + '</span>' +
      badge + icons + '</div>';
  }

  window.showAddForm = function () {
    _editingId = null;
    document.getElementById('loc-id').value = '';
    document.getElementById('loc-name').value = '';
    document.getElementById('loc-slug').value = '';
    document.getElementById('loc-form-title').textContent = 'Add Location';
    document.getElementById('loc-form-container').classList.remove('hidden');
  };

  window.hideForm = function () {
    document.getElementById('loc-form-container').classList.add('hidden');
  };

  window._locEdit = function (id) {
    var loc = (window._locs || []).find(function (l) { return l.id === id; });
    if (!loc) return;
    _editingId = id;
    document.getElementById('loc-id').value = id;
    document.getElementById('loc-name').value = loc.title || '';
    document.getElementById('loc-slug').value = loc.slug || '';
    document.getElementById('loc-type').value = loc.location_type || 'other';
    document.getElementById('loc-privacy').value = loc.privacy_level || 'private';
    document.getElementById('loc-form-title').textContent = 'Edit Location';
    document.getElementById('loc-form-container').classList.remove('hidden');
  };

  var formEl = document.getElementById('loc-form');
  if (formEl) {
    formEl.addEventListener('submit', async function (e) {
      e.preventDefault();
      var idv = document.getElementById('loc-id').value;
      var payload = {
        slug: document.getElementById('loc-slug').value,
        title: document.getElementById('loc-name').value,
        location_type: document.getElementById('loc-type').value,
        privacy_level: document.getElementById('loc-privacy').value,
      };
      var method = idv ? 'PUT' : 'POST';
      var url = idv ? '/api/v2/locations/' + idv : '/api/v2/locations';
      var r = await fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (r.ok) {
        var listR = await fetch('/api/v2/locations');
        window._locs = await listR.json();
        renderList();
        hideForm();
      } else {
        var err = await r.json();
        alert(err.detail || 'Error');
      }
    });
  }

  window._locArchive = async function (id) {
    if (!confirm('Archive this location?')) return;
    await fetch('/api/v2/locations/' + id + '/archive', { method: 'POST' });
    var r = await fetch('/api/v2/locations');
    window._locs = await r.json();
    renderList();
  };

  window._locDelete = async function (id) {
    if (!confirm('Delete this location permanently?')) return;
    var r = await fetch('/api/v2/locations/' + id, { method: 'DELETE' });
    if (!r.ok) {
      var err = await r.json();
      alert(err.detail || 'Cannot delete');
      return;
    }
    var listR = await fetch('/api/v2/locations');
    window._locs = await listR.json();
    renderList();
  };

  function escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }
})();
