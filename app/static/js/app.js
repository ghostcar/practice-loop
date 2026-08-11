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

  // HTMX: auto-include CSRF token in all state-changing requests
  document.addEventListener('DOMContentLoaded', function () {
    document.body.addEventListener('htmx:configRequest', function (evt) {
      var token = document.querySelector('meta[name="csrf-token"]');
      if (token) evt.detail.headers['X-CSRF-Token'] = token.content;
    });

    // HTMX live region: announce after-swap events
    var live = document.getElementById('htmx-live-region');
    document.body.addEventListener('htmx:afterSwap', function (evt) {
      if (live && evt.detail && evt.detail.target) {
        live.textContent = 'Updated ' + (evt.detail.target.id || 'region');
      }
    });
  });

  // XSS-safe HTML escaping helper (mirrors the old inline helper).
  window.escapeHtml = function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  };
})();
