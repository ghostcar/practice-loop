// Import page: drag&drop upload UX + result banner (extracted from import_data.html, DESIGN.md 15.4).
// i18n strings come from the <script type="application/json" id="page-i18n"> block.
(function () {
  'use strict';
  let T = {};
  try {
    const el = document.getElementById('page-i18n');
    if (el) T = JSON.parse(el.textContent) || {};
  } catch (e) {
    console.warn('Import page i18n:', e);
  }

  const zone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const fileName = document.getElementById('file-name');
  const uploadBtn = document.getElementById('upload-btn');
  const resultEl = document.getElementById('upload-result');
  if (!zone || !fileInput) return;

  function updateFileName() {
    if (fileInput.files && fileInput.files.length > 0) {
      fileName.textContent = fileInput.files[0].name;
      fileName.classList.remove('hidden');
      uploadBtn.disabled = false;
    } else {
      fileName.classList.add('hidden');
      uploadBtn.disabled = true;
    }
  }

  fileInput.addEventListener('change', updateFileName);

  ['dragenter', 'dragover'].forEach(function (ev) {
    zone.addEventListener(ev, function (e) {
      e.preventDefault();
      zone.classList.remove('border-slate-200', 'dark:border-slate-700');
      zone.classList.add('border-indigo-400', 'dark:border-indigo-500', 'bg-indigo-50/50', 'dark:bg-indigo-900/10');
    });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    zone.addEventListener(ev, function (e) {
      e.preventDefault();
      zone.classList.add('border-slate-200', 'dark:border-slate-700');
      zone.classList.remove('border-indigo-400', 'dark:border-indigo-500', 'bg-indigo-50/50', 'dark:bg-indigo-900/10');
    });
  });
  zone.addEventListener('drop', function (e) {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      fileInput.files = e.dataTransfer.files;
      updateFileName();
    }
  });

  // The upload endpoint returns JSON ({"status","imported","skipped"}); render it nicely.
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (!evt.detail || !evt.detail.target || evt.detail.target.id !== 'upload-result') return;
    var text = (evt.detail.target.textContent || '').trim();
    if (!text) return;
    var data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      // Non-JSON error body (proxy error page etc.) — show raw text.
      resultEl.innerHTML =
        '<div class="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">' +
        escapeHtml(text) +
        '</div>';
      return;
    }
    var html;
    if (data.status === 'ok') {
      var skipped = data.skipped || 0;
      html =
        '<div class="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300 flex items-center gap-2">' +
        '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 13l4 4L19 7"/></svg>' +
        '<span>' +
        escapeHtml(data.imported) +
        ' ' +
        escapeHtml(T.import_result_imported || 'imported') +
        '</span>' +
        (skipped > 0
          ? '<span class="text-amber-600 dark:text-amber-400">' + escapeHtml(skipped) + ' ' + escapeHtml(T.import_result_skipped || 'skipped') + '</span>'
          : '') +
        '</div>';
    } else {
      html =
        '<div class="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">' +
        escapeHtml(T.import_result_error || 'Import failed') +
        ': ' +
        escapeHtml(data.detail || data.message || '') +
        '</div>';
    }
    resultEl.innerHTML = html;
  });
})();
