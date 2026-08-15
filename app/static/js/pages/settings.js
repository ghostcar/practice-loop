/**
 * Settings page (Step 9e, DESIGN_V2 §16) — dashboard block reorder.
 *
 * Keeps two hidden inputs in sync with the DOM:
 *   #block-order  — comma-joined render order of all blocks
 *   #block-hidden — comma-joined list of unchecked (hidden) blocks
 * Supports arrow buttons and HTML5 drag & drop; no inline scripts.
 */
(function () {
  'use strict';

  function init() {
    var list = document.getElementById('dash-blocks');
    var orderInput = document.getElementById('block-order');
    var hiddenInput = document.getElementById('block-hidden');
    if (!list || !orderInput || !hiddenInput) return;

    function sync() {
      var order = [];
      var hidden = [];
      var items = list.querySelectorAll('li[data-block]');
      for (var i = 0; i < items.length; i++) {
        var block = items[i].getAttribute('data-block');
        order.push(block);
        var cb = items[i].querySelector('input[data-visible]');
        if (cb && !cb.checked) hidden.push(block);
      }
      orderInput.value = order.join(',');
      hiddenInput.value = hidden.join(',');
    }

    // Arrow buttons
    list.addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-move]');
      if (!btn) return;
      var li = btn.closest('li[data-block]');
      if (!li) return;
      var dir = parseInt(btn.getAttribute('data-move'), 10) || 0;
      if (dir < 0 && li.previousElementSibling) {
        list.insertBefore(li, li.previousElementSibling);
      } else if (dir > 0 && li.nextElementSibling) {
        list.insertBefore(li.nextElementSibling, li);
      }
      sync();
    });

    // Visibility checkboxes
    list.addEventListener('change', function (e) {
      if (e.target.matches && e.target.matches('input[data-visible]')) sync();
    });

    // HTML5 drag & drop
    var dragEl = null;
    list.addEventListener('dragstart', function (e) {
      var li = e.target.closest('li[data-block]');
      if (!li) return;
      dragEl = li;
      li.classList.add('opacity-60');
      try { e.dataTransfer.effectAllowed = 'move'; } catch (err) { /* ignore */ }
    });
    list.addEventListener('dragend', function () {
      if (dragEl) dragEl.classList.remove('opacity-60');
      dragEl = null;
      sync();
    });
    list.addEventListener('dragover', function (e) {
      e.preventDefault();
      var li = e.target.closest('li[data-block]');
      if (!li || li === dragEl) return;
      var rect = li.getBoundingClientRect();
      var after = (e.clientY - rect.top) > rect.height / 2;
      if (after) {
        if (li.nextElementSibling !== dragEl) list.insertBefore(dragEl, li.nextElementSibling);
      } else if (li !== dragEl) {
        list.insertBefore(dragEl, li);
      }
    });
    list.addEventListener('drop', function (e) { e.preventDefault(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
