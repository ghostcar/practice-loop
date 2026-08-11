// Body Parts catalog page: tree rendering, search, filter (DESIGN.md 15.4).
(function () {
  'use strict';

  var treeEl = document.getElementById('bp-tree');
  if (!treeEl) return;

  // Fetch tree on load
  (async function () {
    try {
      var r = await fetch('/api/v2/body-parts/tree');
      var tree = await r.json();
      window._bpTree = tree;
      window._bpFlat = flattenTree(tree);
      renderTree(tree);
    } catch (e) {
      treeEl.innerHTML = '<div class="p-4 text-sm text-red-400">Failed to load body parts</div>';
    }
  })();

  function flattenTree(nodes, out) {
    out = out || [];
    for (var i = 0; i < nodes.length; i++) {
      out.push(nodes[i]);
      if (nodes[i].children) flattenTree(nodes[i].children, out);
    }
    return out;
  }

  window.filterTree = function () {
    var q = (document.getElementById('bp-search').value || '').toLowerCase();
    var sys = document.getElementById('bp-system').value;
    var filtered = window._bpFlat || [];
    if (sys) filtered = filtered.filter(function (n) { return n.body_system === sys; });
    if (q) {
      filtered = filtered.filter(function (n) {
        return (n.title || '').toLowerCase().indexOf(q) !== -1 ||
               (n.slug || '').toLowerCase().indexOf(q) !== -1;
      });
    }
    var ids = {};
    filtered.forEach(function (n) { ids[n.id] = true; });
    renderTree(window._bpTree, ids, q ? true : false);
  };

  function renderTree(nodes, highlightIds, expandAll) {
    treeEl.innerHTML = nodes.map(function (n) { return renderNode(n, 0, highlightIds, expandAll); }).join('');
  }

  function renderNode(node, depth, highlightIds, expandAll) {
    var hasChildren = node.children && node.children.length > 0;
    var highlighted = highlightIds ? highlightIds[node.id] : true;
    if (!highlighted && !hasChildren) return '';
    var indent = depth * 16;
    var dotColor = node.is_sensitive ? 'bg-rose-400' : 'bg-slate-300 dark:bg-slate-600';
    var id = 'bp-' + node.id;
    var html = '<div class="flex items-center gap-2 px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors' +
      (highlighted ? '' : ' opacity-30') + '" style="padding-left:' + (indent + 16) + 'px">';
    if (hasChildren) {
      html += '<button onclick="window._bpToggle(\'' + id + '\')\" class="w-5 h-5 flex items-center justify-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-xs transition-transform\" id=\"' + id + '-btn\">\u25b8</button>';
    } else {
      html += '<span class="w-5"></span>';
    }
    html += '<span class="w-2 h-2 rounded-full ' + dotColor + ' flex-shrink-0"></span>';
    html += '<span class="text-sm text-slate-700 dark:text-slate-200">' + escHtml(node.title) + '</span>';
    html += '<span class="text-xs text-slate-400 ml-auto">' + escHtml(node.slug || '') + '</span>';
    html += '</div>';
    if (hasChildren) {
      html += '<div id="' + id + '" class="' + (expandAll ? '' : 'hidden') + '">';
      html += node.children.map(function (c) { return renderNode(c, depth + 1, highlightIds, expandAll); }).join('');
      html += '</div>';
    }
    return html;
  }

  window._bpToggle = function (id) {
    var el = document.getElementById(id);
    var btn = document.getElementById(id + '-btn');
    if (el) {
      el.classList.toggle('hidden');
      if (btn) btn.textContent = el.classList.contains('hidden') ? '\u25b8' : '\u25be';
    }
  };

  function escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }
})();
