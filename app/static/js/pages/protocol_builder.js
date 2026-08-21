(function () {
  'use strict';
  var canvas = document.getElementById('steps-canvas');
  var jsonOut = document.getElementById('steps-json');
  if (!canvas || !jsonOut) return;

  var configEl = document.getElementById('protocol-builder-config');
  var config = configEl ? JSON.parse(configEl.textContent || '{}') : {};
  var STEP_TYPES = config.step_types || [];
  var TIMING_TYPES = config.timing_types || [];
  var i18n = config.i18n || {};

  var UNIT_SECONDS = { months: 2592000, days: 86400, hours: 3600, minutes: 60, seconds: 1 };

  function rowDurationSeconds(row) {
    var total = 0;
    Object.keys(UNIT_SECONDS).forEach(function (unit) {
      var input = row.querySelector('input[name$="_' + unit + '"]');
      if (input) total += (Number(input.value) || 0) * UNIT_SECONDS[unit];
    });
    return total;
  }

  function collect() {
    var rows = canvas.querySelectorAll('.step-row');
    var steps = [];
    rows.forEach(function (row, idx) {
      var title = row.querySelector('.step-title').value.trim();
      if (!title) return;
      steps.push({
        title: title,
        step_type: row.querySelector('.step-type').value,
        timing_spec: {
          type: row.querySelector('.step-timing').value,
          offset_seconds: Number(row.querySelector('.step-offset').value) || 0
        },
        custom_params: { duration_seconds: rowDurationSeconds(row) }
      });
    });
    jsonOut.value = JSON.stringify(steps);
  }

  function renumber() {
    canvas.querySelectorAll('.step-row').forEach(function (row, idx) {
      row.dataset.idx = idx;
      row.querySelector('.step-num').textContent = idx + 1;
      row.querySelectorAll('input[name]').forEach(function () {});
    });
  }

  function makeRow() {
    var idx = canvas.querySelectorAll('.step-row').length;
    var row = document.createElement('div');
    row.className = 'step-row p-4 rounded-xl bg-[color:var(--surface-soft)] border border-[color:var(--border)] space-y-3';
    row.dataset.idx = idx;
    var typeOpts = STEP_TYPES.map(function (st) { return '<option value="' + st + '">' + st + '</option>'; }).join('');
    var timingOpts = TIMING_TYPES.map(function (tt) { return '<option value="' + tt + '">' + tt + '</option>'; }).join('');
    var unitLabels = ['months', 'days', 'hours', 'minutes', 'seconds'].map(function (unit) {
      return '<label class="flex flex-col gap-0.5">' +
        '<span class="text-[10px] text-[color:var(--text-muted)]">' + (i18n['dp_' + unit] || unit) + '</span>' +
        '<input type="number" min="0" step="1" name="step_' + idx + '_' + unit + '" value="0" class="w-full px-1.5 py-1.5 rounded-lg bg-[color:var(--surface)] border border-[color:var(--border)] text-xs text-[color:var(--text)] min-h-[34px]">' +
      '</label>';
    }).join('');
    var presets = [["10с", 10], ["30с", 30], ["60с", 60], ["2м", 120], ["5м", 300], ["15м", 900], ["30м", 1800], ["1ч", 3600], ["2ч", 7200], ["24ч", 86400], ["7д", 604800], ["30д", 2592000]].map(function (p) {
      return '<button type="button" class="dp-preset px-2 py-1 rounded-lg text-[11px] font-medium pl-surface-soft border border-[color:var(--border)] text-[color:var(--text-secondary)] hover:border-[color:var(--accent)] hover:text-[color:var(--text)] transition-colors" data-seconds="' + p[1] + '">' + p[0] + '</button>';
    }).join('');
    row.innerHTML =
      '<div class="flex items-center gap-2 justify-between">' +
        '<span class="step-num text-xs font-bold text-[color:var(--accent)]">' + (idx + 1) + '</span>' +
        '<button type="button" class="remove-step text-rose-400 hover:bg-rose-500/10 rounded-lg p-1" title="' + (i18n.remove_step || 'Remove step') + '"></button>' +
      '</div>' +
      '<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">' +
        '<label class="flex flex-col gap-1"><span class="text-xs font-semibold text-[color:var(--text-muted)]">' + (i18n.step_title || 'Название шага') + '</span>' +
          '<input type="text" class="step-title px-3 py-2 rounded-lg bg-[color:var(--surface)] border border-[color:var(--border)] text-sm text-[color:var(--text)]" placeholder="' + (i18n.step_title_ph || '') + '"></label>' +
        '<label class="flex flex-col gap-1"><span class="text-xs font-semibold text-[color:var(--text-muted)]">' + (i18n.step_type || 'Тип шага') + '</span>' +
          '<select class="step-type px-3 py-2 rounded-lg bg-[color:var(--surface)] border border-[color:var(--border)] text-sm text-[color:var(--text)]">' + typeOpts + '</select></label>' +
      '</div>' +
      '<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">' +
        '<label class="flex flex-col gap-1"><span class="text-xs font-semibold text-[color:var(--text-muted)]">' + (i18n.step_timing || 'Тайминг') + '</span>' +
          '<select class="step-timing px-3 py-2 rounded-lg bg-[color:var(--surface)] border border-[color:var(--border)] text-sm text-[color:var(--text)]">' + timingOpts + '</select></label>' +
        '<label class="flex flex-col gap-1"><span class="text-xs font-semibold text-[color:var(--text-muted)]">' + (i18n.step_offset || 'Смещение (сек)') + '</span>' +
          '<input type="number" min="0" step="1" class="step-offset px-3 py-2 rounded-lg bg-[color:var(--surface)] border border-[color:var(--border)] text-sm text-[color:var(--text)]" value="0"></label>' +
      '</div>' +
      '<div>' +
        '<span class="text-xs font-semibold text-[color:var(--text-muted)]">' + (i18n.step_duration || 'Длительность') + '</span>' +
        '<div class="mt-1.5 duration-picker space-y-3">' +
          '<div class="grid grid-cols-5 gap-1.5">' + unitLabels + '</div>' +
          '<div class="flex flex-wrap items-center gap-1.5">' +
            '<span class="text-[10px] uppercase tracking-wide text-[color:var(--text-muted)] font-semibold">' + (i18n.dp_presets || 'Быстрые пресеты') + ':</span>' + presets +
          '</div>' +
        '</div>' +
      '</div>' +
      '<input type="hidden" class="step-duration-json" name="" value="">';
    canvas.appendChild(row);
    var dpRoot = row.querySelector('.duration-picker');
    if (dpRoot) {
      dpRoot.querySelectorAll('.dp-preset').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var rest = Number(btn.dataset.seconds) || 0;
          ['months', 'days', 'hours', 'minutes', 'seconds'].forEach(function (unit) {
            var input = dpRoot.querySelector('input[name$="_' + unit + '"]');
            if (!input) return;
            input.value = Math.floor(rest / UNIT_SECONDS[unit]);
            rest = rest % UNIT_SECONDS[unit];
          });
          collect();
        });
      });
    }
    var rmBtn = row.querySelector('.remove-step');
    if (rmBtn && window.plIcon) rmBtn.appendChild(window.plIcon('close', 'w-4 h-4'));
    renumber();
    collect();
  }

  var addBtn = document.getElementById('add-step');
  if (addBtn) addBtn.addEventListener('click', makeRow);

  canvas.addEventListener('click', function (ev) {
    var btn = ev.target.closest('.remove-step');
    if (!btn) return;
    btn.closest('.step-row').remove();
    renumber();
    collect();
  });
  canvas.addEventListener('input', collect);
  canvas.addEventListener('change', collect);
  var form = document.querySelector('form');
  if (form) form.addEventListener('submit', collect);
})();
