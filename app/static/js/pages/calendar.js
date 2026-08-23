// Calendar page: templates, overrides, availability check (extracted from calendar.html, DESIGN.md 15.4).
// i18n strings come from the <script type="application/json" id="page-i18n"> block.
(function () {
  'use strict';
  let T = {};
  try {
    const el = document.getElementById('page-i18n');
    if (el) T = JSON.parse(el.textContent) || {};
  } catch (e) {
    console.warn('Calendar page i18n:', e);
  }
  const I18N = {
    calendar_no_templates: T.calendar_no_templates || '',
    calendar_no_overrides: T.calendar_no_overrides || '',
    calendar_default_marker: '(' + (T.calendar_form_set_default || '').trim() + ')',
    calendar_window_count: (T.calendar_form_label_ph || '').trim(),
    calendar_check_available: T.calendar_result_available || '',
    calendar_check_unavailable: T.calendar_result_unavailable || '',
    calendar_btn_delete: T.calendar_btn_delete || 'Delete',
  };
  const POLICY_LABEL = {
    allowed: T.calendar_policy_allowed || 'Allowed',
    passive_only: T.calendar_policy_passive || 'Passive only',
    disallowed: T.calendar_policy_disallowed || 'Blocked',
  };

  const root = document.getElementById('template-list');
  if (!root) return;

  async function loadData() {
    const tRes = await fetch('/calendar/templates');
    const templates = await tRes.json();
    const defaultSuffix = ' ' + I18N.calendar_default_marker + ' ';
    const winSuffix = ' ' + I18N.calendar_window_count + '';
    document.getElementById('template-list').innerHTML =
      templates
        .map(
          (t) =>
            `<div class="flex justify-between items-center py-0.5"><span class="text-slate-600 dark:text-[color:var(--text-muted)]">${escapeHtml(t.name)}${t.is_default ? defaultSuffix : ''} &mdash; ${t.windows.length}${winSuffix}</span><button data-action="delTpl" data-arg1="${escapeHtml(String(t.id))}" class="text-red-700 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-xs">${escapeHtml(I18N.calendar_btn_delete)}</button></div>`
        )
        .join('') || '<span class="text-[color:var(--text-muted)]">' + escapeHtml(I18N.calendar_no_templates) + '</span>';

    const sel = document.getElementById('ovr-tpl');
    sel.innerHTML = templates.map((t) => `<option value="${escapeHtml(String(t.id))}">${escapeHtml(t.name)}</option>`).join('');

    const oRes = await fetch('/calendar/overrides');
    const overrides = await oRes.json();
    document.getElementById('override-list').innerHTML =
      overrides
        .map(
          (o) =>
            `<div class="flex justify-between items-center py-0.5"><span class="text-slate-600 dark:text-[color:var(--text-muted)]">${escapeHtml(String(o.label || o.template_name))}: ${o.start_date} &rarr; ${o.end_date}</span><button data-action="delOvr" data-arg1="${escapeHtml(String(o.id))}" class="text-red-700 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-xs">${escapeHtml(I18N.calendar_btn_delete)}</button></div>`
        )
        .join('') || '<span class="text-[color:var(--text-muted)]">' + escapeHtml(I18N.calendar_no_overrides) + '</span>';
  }

  async function saveTemplate() {
    const name = document.getElementById('tpl-name').value;
    const isDefault = document.getElementById('tpl-default').checked;
    const rows = document.querySelectorAll('.window-row');
    const windows = Array.from(rows).map((r) => ({
      day_of_week: parseInt(r.querySelector('.dow').value),
      start_time: r.querySelector('.st').value,
      end_time: r.querySelector('.et').value,
      label: r.querySelector('.lb').value,
      policy: r.querySelector('.pol').value,
    }));
    await fetch('/calendar/templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, is_default: isDefault, windows }),
    });
    document.getElementById('template-form').classList.add('hidden');
    loadData();
    location.reload();
  }

  async function saveOverride() {
    const body = {
      template_id: document.getElementById('ovr-tpl').value,
      start_date: document.getElementById('ovr-start').value,
      end_date: document.getElementById('ovr-end').value,
      label: document.getElementById('ovr-label').value || null,
    };
    await fetch('/calendar/overrides', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    document.getElementById('override-form').classList.add('hidden');
    loadData();
  }

  async function delTpl(id) {
    await fetch(`/calendar/templates/${id}`, { method: 'DELETE' });
    loadData();
  }
  async function delOvr(id) {
    await fetch(`/calendar/overrides/${id}`, { method: 'DELETE' });
    loadData();
  }

  function showTemplateForm() {
    document.getElementById('template-form').classList.toggle('hidden');
  }
  function showOverrideForm() {
    document.getElementById('override-form').classList.toggle('hidden');
  }
  function addWindowRow() {
    const row = document.querySelector('.window-row').cloneNode(true);
    document.getElementById('tpl-windows').appendChild(row);
  }

  const checkForm = document.getElementById('check-form');
  if (checkForm) {
    checkForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const dt = document.getElementById('check-dt').value;
      const intensity = document.getElementById('check-intensity').value;
      const res = await fetch(`/calendar/check?target_time=${dt}&intensity=${intensity}&duration=60`);
      const data = await res.json();
      const el = document.getElementById('check-result');
      const policyLabel = POLICY_LABEL[data.policy] || data.policy;
      el.innerHTML = data.available
        ? `<span class="text-emerald-700 dark:text-emerald-400 font-medium">${escapeHtml(I18N.calendar_check_available)}</span> <span class="text-[color:var(--text-secondary)]">(${escapeHtml(policyLabel)}${data.window_label ? ', ' + escapeHtml(data.window_label) : ''})</span>`
        : `<span class="text-red-700 dark:text-red-400 font-medium">${escapeHtml(I18N.calendar_check_unavailable)}</span> <span class="text-[color:var(--text-secondary)]">(${escapeHtml(policyLabel)}${data.window_label ? ', ' + escapeHtml(data.window_label) : ''}${data.reason ? ' — ' + escapeHtml(data.reason) : ''})</span>`;
    });
  }

  const checkDt = document.getElementById('check-dt');
  if (checkDt) checkDt.value = window.localNowLocalInput();
  loadData();

  // Exposed for inline onclick handlers in the template.
  window.addWindowRow = addWindowRow;
  window.delOvr = delOvr;
  window.delTpl = delTpl;
  window.saveOverride = saveOverride;
  window.saveTemplate = saveTemplate;
  window.showOverrideForm = showOverrideForm;
  window.showTemplateForm = showTemplateForm;
})();
