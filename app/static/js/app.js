/**
 * Shared bootstrap (DESIGN.md 15.4 — no inline scripts except a tiny
 * nonce-less bootstrap hook in base.html that loads this file).
 *
 * Responsibilities:
 *  - attach X-CSRF-Token to every same-origin state-changing fetch();
 *  - auto-include CSRF token in HTMX requests;
 *  - XSS-safe escapeHtml() helper;
 *  - HTMX live-region announcements.
 */
(function () {
  'use strict';

  // Detect the device's IANA timezone and persist it in a `client_tz` cookie
  // so the server can compute day-boundaries ("today") in the user's local
  // calendar day. Graceful: Intl unavailable → no cookie → UTC fallback.
  try {
    var deviceTz = (Intl.DateTimeFormat().resolvedOptions().timeZone) || '';
    if (deviceTz) {
      window.clientTz = deviceTz;
      var parts = ('; ' + document.cookie).split('; client_tz=');
      var prev = parts.length === 2 ? parts.pop().split(';')[0] : '';
      if (prev !== deviceTz) {
        var expiry = new Date(Date.now() + 365 * 24 * 3600 * 1000).toUTCString();
        document.cookie = 'client_tz=' + encodeURIComponent(deviceTz) +
          '; path=/; expires=' + expiry + '; SameSite=Lax';
      }
    }
  } catch (e) { /* ignore */ }

  // Theme choice (Step 9e, DESIGN_V2 §16): 'system' resolves to the OS
  // preference. The server renders data-theme with a fallback resolution and
  // keeps the raw choice in data-theme-choice; this reconciles the two and
  // follows live OS changes. 'dark'/'light' are applied as-is.
  var htmlEl = document.documentElement;
  function applyThemeChoice() {
    var choice = htmlEl.getAttribute('data-theme-choice') || 'dark';
    var resolved = choice;
    if (choice === 'system') {
      resolved = (window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark';
    }
    if (resolved !== 'dark' && resolved !== 'light') resolved = 'dark';
    htmlEl.setAttribute('data-theme', resolved);
    htmlEl.classList.toggle('dark', resolved === 'dark');
    htmlEl.classList.toggle('light', resolved === 'light');
  }
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
  if (mq && mq.addEventListener) {
    mq.addEventListener('change', function () {
      if ((htmlEl.getAttribute('data-theme-choice') || 'dark') === 'system') applyThemeChoice();
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyThemeChoice);
  } else {
    applyThemeChoice();
  }

  // CSRF: attach the X-CSRF-Token header to every same-origin
  // state-changing fetch() call (JSON API pages use plain fetch, not HTMX).
  var origFetch = window.fetch;
  window.fetch = function (input, init) {
    init = init || {};
    var method = (init.method || (input && input.method) || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
      var url = typeof input === 'string' ? input : ((input && input.url) || '');
      var isSameOrigin =
        (typeof input === 'string' && url.charAt(0) === '/' && url.charAt(1) !== '/') ||
        (typeof input !== 'string' && url.indexOf(location.origin) === 0);
      if (isSameOrigin) {
        var headers = new Headers(init.headers || {});
        if (!headers.has('X-CSRF-Token')) {
          var meta = document.querySelector('meta[name="csrf-token"]');
          if (meta) headers.set('X-CSRF-Token', meta.content);
        }
        init.headers = headers;
      }
    }
    return origFetch.call(this, input, init);
  };

  // Device-timezone-aware <time> rendering: the backend emits
  // <time datetime="...(+00:00)" data-tz-fmt="%Y-%m-%d %H:%M">…</time>
  // and this rewrites the visible text to the device's local timezone.
  // Rewrites a backend UTC instant into device-local text. Supported fmt
  // tokens: %Y %m %d %H %M %S. Weekday/month names (%A/%B/%a/%b) are NOT
  // handled here — date-only values are rendered server-side by _localtime.
  function formatLocalTime(iso, fmt) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    return fmt.replace(/%([YmdHMS])/g, function (_m, k) {
      switch (k) {
        case 'Y': return String(d.getFullYear());
        case 'm': return pad(d.getMonth() + 1);
        case 'd': return pad(d.getDate());
        case 'H': return pad(d.getHours());
        case 'M': return pad(d.getMinutes());
        case 'S': return pad(d.getSeconds());
        default: return _m;
      }
    });
  }

  function applyLocalTimezones(root) {
    var els = (root || document).querySelectorAll('time[data-tz-fmt]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var iso = el.getAttribute('datetime');
      var fmt = el.getAttribute('data-tz-fmt');
      if (!iso || !fmt) continue;
      var text = formatLocalTime(iso, fmt);
      if (text) {
        el.textContent = text;
        el.title = 'UTC ' + iso.replace('T', ' ').slice(0, 16);
      }
    }
  }

  // HTMX: auto-include CSRF token in all state-changing requests
  document.addEventListener('DOMContentLoaded', function () {
    applyLocalTimezones(document);
    document.body.addEventListener('htmx:configRequest', function (evt) {
      var token = document.querySelector('meta[name="csrf-token"]');
      if (token) evt.detail.headers['X-CSRF-Token'] = token.content;
    });

    // Re-render device-local times after every HTMX swap
    document.body.addEventListener('htmx:afterSwap', function () {
      applyLocalTimezones(document);
    });

    // CSP enforcing (ADR-151): inline event handlers are forbidden, so page
    // code uses data-action/data-change/data-input + data-confirm attributes.
    // Delegated listeners call the global page functions (window.*) with
    // JSON-encoded data-args ("$this" is replaced with the element).
    document.addEventListener('click', function (e) {
      var el = e.target.closest('[data-action]');
      if (!el) return;
      // Confirm-buttons: ask before letting the enclosing form submit.
      if (el.hasAttribute('data-confirm')) {
        if (!window.confirm(el.getAttribute('data-confirm'))) {
          e.preventDefault();
          return;
        }
      }
      var action = el.getAttribute('data-action');
      if (action === 'historyBack') { history.back(); return; }
      if (action === 'copyImportUrl') {
        var u = el.getAttribute('data-arg1') || '';
        navigator.clipboard.writeText(u).catch(function () {});
        return;
      }
      var fn = window[action];
      if (typeof fn !== 'function') return;
      var args = [];
      try { args = JSON.parse(el.getAttribute('data-args') || '[]'); } catch (err) { args = []; }
      if (!args.length && el.hasAttribute('data-arg1')) {
        for (var i = 1; i <= 9; i++) {
          var v = el.getAttribute('data-arg' + i);
          if (v === null) break;
          args.push(v);
        }
      }
      for (var j = 0; j < args.length; j++) {
        if (args[j] === '$this') args[j] = el;
      }
      fn.apply(el, args);
    });
    document.addEventListener('change', function (e) {
      var el = e.target.closest('[data-change]');
      if (!el) return;
      var fn = window[el.getAttribute('data-change')];
      if (typeof fn === 'function') fn.call(el);
    });
    document.addEventListener('input', function (e) {
      var el = e.target.closest('[data-input]');
      if (!el) return;
      var fn = window[el.getAttribute('data-input')];
      if (typeof fn === 'function') fn.call(el);
    });
    document.addEventListener('submit', function (e) {
      var form = e.target.closest('form[data-confirm]');
      if (form && !window.confirm(form.getAttribute('data-confirm'))) {
        e.preventDefault();
      }
    });

    // HTMX live region: announce after-swap events
    var live = document.getElementById('htmx-live-region');
    document.body.addEventListener('htmx:afterSwap', function (evt) {
      if (live && evt.detail && evt.detail.target) {
        live.textContent = 'Updated ' + (evt.detail.target.id || 'region');
      }
    });
  });

  // Device-local "today" helpers. `toISOString()` yields UTC, which drifts a
  // day for devices west of UTC near midnight — so default date/datetime
  // inputs must be derived from local getters, not ISO/UTC.
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  window.localTodayISO = function localTodayISO() {
    var d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  };
  // Convert an ISO instant to the device-local calendar date (YYYY-MM-DD).
  // Expects an offset-bearing ISO string (e.g. "...+00:00" or "Z"); the API
  // serializes timezone-aware datetimes, so naive strings should never appear.
  window.localDateISO = function localDateISO(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  };
  window.localNowLocalInput = function localNowLocalInput() {
    var d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
      'T' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  };

  // XSS-safe HTML escaping helper (mirrors the old inline helper).
  window.escapeHtml = function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  };

  // PracticeLoop icon pack helper (design/icons/INTEGRATION_AGENT.md §6).
  // Creates an <svg><use> icon via DOM APIs — never via innerHTML — with
  // currentColor stroke. `name` must come from a static allowlist.
  window.plIcon = function plIcon(name, className) {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', className || 'w-4 h-4');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.75');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    var use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '/static/icons/sprite.svg#icon-' + name);
    svg.appendChild(use);
    return svg;
  };

  // App shell (DESIGN v2 §7): sidebar collapse/expand + mobile nav sheet.
  // Sidebar state persists in localStorage; default collapsed (explicit expand).
  function initShell() {
    var body = document.body;
    var sidebar = document.getElementById('pl-sidebar');
    var toggle = document.getElementById('pl-sidebar-toggle');
    var sheet = document.getElementById('pl-mobile-sheet');
    var menuBtn = document.getElementById('pl-mobile-menu');
    var sheetClose = document.getElementById('pl-mobile-sheet-close');
    var lastFocus = null;

    if (sidebar && toggle) {
      var saved = null;
      try { saved = localStorage.getItem('pl_sidebar'); } catch (e) { /* ignore */ }
      var open = saved === 'expanded';
      var applyState = function () {
        body.classList.toggle('pl-sidebar-open', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        var label = open
          ? toggle.getAttribute('data-label-collapse')
          : toggle.getAttribute('data-label-expand');
        if (label) toggle.setAttribute('aria-label', label);
        try { localStorage.setItem('pl_sidebar', open ? 'expanded' : 'collapsed'); } catch (e) { /* ignore */ }
      };
      toggle.addEventListener('click', function () { open = !open; applyState(); });
      applyState();
    }

    // Discretion quick toggle (Step 9e, DESIGN_V2 §12): POST to the server
    // (source of truth for the next SSR) and apply the visual state instantly
    // — favicon, html[data-discretion] (blur), nav labels, toggle icons.
    var dscrBtns = document.querySelectorAll('#pl-discretion-toggle, #pl-discretion-toggle-m');
    var faviconLink = document.getElementById('pl-favicon');
    // Sensitive-image blur level for client-rendered images (e.g. inventory rows)
    var dscrBlur = parseInt(htmlEl.getAttribute('data-blur') || '0', 10);
    function refreshBlurCls() {
      window.__dscrBlurCls = (htmlEl.getAttribute('data-discretion') === 'on' && dscrBlur > 0)
        ? ' pl-blur-' + dscrBlur : '';
    }
    refreshBlurCls();
    function setDiscretionVisual(on) {
      if (on) htmlEl.setAttribute('data-discretion', 'on');
      else htmlEl.removeAttribute('data-discretion');
      if (faviconLink) {
        faviconLink.href = on ? '/static/favicon/favicon-neutral.svg' : '/static/favicon/favicon.svg';
      }
      var items = document.querySelectorAll('.pl-nav-item[data-dscr]');
      for (var i = 0; i < items.length; i++) {
        var lbl = items[i].querySelector('.pl-nav-label');
        if (lbl) lbl.textContent = on ? items[i].getAttribute('data-dscr') : (items[i].getAttribute('data-label') || lbl.textContent);
      }
    }
    function updateDscrButtonIcons(on) {
      for (var i = 0; i < dscrBtns.length; i++) {
        dscrBtns[i].innerHTML = on
          ? '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="/static/icons/sprite.svg#icon-eye-off"></use></svg>'
          : '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="/static/icons/sprite.svg#icon-eye"></use></svg>';
      }
    }
    for (var bi = 0; bi < dscrBtns.length; bi++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          fetch('/settings/discretion/toggle', { method: 'POST' })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('toggle failed')); })
            .then(function (data) {
              var on = data.mode === 'always';
              setDiscretionVisual(on);
              refreshBlurCls();
              updateDscrButtonIcons(on);
            })
            .catch(function () { /* keep current state */ });
        });
      })(dscrBtns[bi]);
    }

    if (sheet && menuBtn) {
      var openSheet = function () {
        lastFocus = document.activeElement;
        sheet.hidden = false;
        sheet.setAttribute('aria-hidden', 'false');
        menuBtn.setAttribute('aria-expanded', 'true');
        body.style.overflow = 'hidden';
        var closeBtn = sheetClose || sheet.querySelector('button');
        if (closeBtn) closeBtn.focus();
      };
      var closeSheet = function () {
        sheet.hidden = true;
        sheet.setAttribute('aria-hidden', 'true');
        menuBtn.setAttribute('aria-expanded', 'false');
        body.style.overflow = '';
        if (lastFocus && lastFocus.focus) lastFocus.focus();
      };
      menuBtn.addEventListener('click', function () {
        if (sheet.hidden) { openSheet(); } else { closeSheet(); }
      });
      if (sheetClose) sheetClose.addEventListener('click', closeSheet);
      sheet.addEventListener('click', function (e) {
        if (e.target === sheet) closeSheet(); // backdrop
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !sheet.hidden) closeSheet();
      });
    }

    // User Profile Dropdown toggle
    var userMenuBtn = document.getElementById('user-menu-btn');
    var userMenuDropdown = document.getElementById('user-menu-dropdown');
    if (userMenuBtn && userMenuDropdown) {
      userMenuBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        var isExpanded = userMenuBtn.getAttribute('aria-expanded') === 'true';
        userMenuBtn.setAttribute('aria-expanded', isExpanded ? 'false' : 'true');
        userMenuDropdown.classList.toggle('hidden', isExpanded);
      });
      document.addEventListener('click', function (e) {
        if (!userMenuDropdown.contains(e.target) && !userMenuBtn.contains(e.target)) {
          userMenuDropdown.classList.add('hidden');
          userMenuBtn.setAttribute('aria-expanded', 'false');
        }
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !userMenuDropdown.classList.contains('hidden')) {
          userMenuDropdown.classList.add('hidden');
          userMenuBtn.setAttribute('aria-expanded', 'false');
          userMenuBtn.focus();
        }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initShell);
  } else {
    initShell();
  }
})();
