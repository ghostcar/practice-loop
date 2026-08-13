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
})();
