// Body-zone reference: localized grouped list, search, and area filter.
(function () {
  'use strict';

  var treeEl = document.getElementById('bp-tree');
  if (!treeEl) return;

  var locale = treeEl.dataset.locale || 'ru';
  var systemLabels = {};
  var systemSelect = document.getElementById('bp-system');
  Array.prototype.forEach.call(systemSelect.options, function (option) {
    if (option.value) systemLabels[option.value] = option.textContent;
  });

  (async function () {
    try {
      var r = await fetch('/api/v2/body-parts/tree');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var tree = await r.json();
      window._bpTree = tree;
      renderGroups(tree);
    } catch (e) {
      treeEl.innerHTML = '<div class="p-4 text-sm text-red-700 dark:text-red-400" role="alert">' +
        escHtml(treeEl.dataset.loadError || '') + '</div>';
    }
  })();

  window.filterTree = function () {
    var q = (document.getElementById('bp-search').value || '').trim().toLowerCase();
    renderGroups(window._bpTree || [], q, systemSelect.value);
  };

  function renderGroups(nodes, query, selectedSystem) {
    var grouped = {};
    (nodes || []).forEach(function (node) {
      var system = node.body_system || 'general';
      if (!grouped[system]) grouped[system] = [];
      grouped[system].push(node);
    });

    var order = Array.prototype.map.call(systemSelect.options, function (option) { return option.value; });
    var html = order.filter(Boolean).map(function (system) {
      if (selectedSystem && selectedSystem !== system) return '';
      var rows = (grouped[system] || []).map(function (node) {
        return renderNode(node, 0, query || '');
      }).join('');
      if (!rows) return '';
      return '<section class="border-b border-[color:var(--border)] last:border-b-0" data-body-system="' +
        escHtml(system) + '">' +
        '<h2 class="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-[color:var(--text-secondary)] pl-surface-soft">' +
        escHtml(systemLabels[system] || systemLabels.general || '') + '</h2>' +
        '<ul class="divide-y divide-[color:var(--border)]" role="list">' + rows + '</ul></section>';
    }).join('');

    treeEl.innerHTML = html || '<div class="p-6 text-center text-sm text-[color:var(--text-muted)]">' +
      escHtml(treeEl.dataset.empty || '') + '</div>';
  }

  function renderNode(node, depth, query) {
    var hasChildren = node.children && node.children.length > 0;
    var title = getTitle(node);
    var matches = !query || searchableTitle(node).indexOf(query) !== -1;
    var childRows = hasChildren ? node.children.map(function (child) {
      return renderNode(child, depth + 1, matches ? '' : query);
    }).join('') : '';
    if (!matches && !childRows) return '';

    var html = '<li><div class="flex min-h-11 items-center gap-3 px-4 py-2.5" style="padding-left:' +
      (16 + depth * 24) + 'px">';
    html += '<span class="w-1.5 h-1.5 rounded-full bg-[color:var(--text-muted)] flex-shrink-0" aria-hidden="true"></span>';
    html += '<span class="text-sm ' + (hasChildren ? 'font-medium' : '') + ' text-[color:var(--text)]">' +
      escHtml(title) + '</span>';
    if (node.is_sensitive) {
      html += '<span class="ml-auto rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">' +
        escHtml(treeEl.dataset.sensitive || '') + '</span>';
    }
    html += '</div>';
    if (hasChildren) {
      html += '<ul class="border-t border-[color:var(--border)] divide-y divide-[color:var(--border)]" role="list">' +
        childRows + '</ul>';
    }
    return html + '</li>';
  }

  function getTitle(node) {
    if (locale.indexOf('en') === 0 && node.title_en) return node.title_en;
    return node.title_ru || node.title_en || '';
  }

  function searchableTitle(node) {
    return String(getTitle(node) + ' ' + (node.title_ru || '') + ' ' + (node.title_en || '')).toLowerCase();
  }

  function escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }
})();
