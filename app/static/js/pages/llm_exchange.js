// External Model Exchange Hub (extracted from llm_exchange.html, R10.2).
// CSRF-токен читается из <meta name="csrf-token"> (base.html), как в tasks.js.

function _llmCsrfToken() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.getAttribute('content') : '';
}

async function generateAndCopyPrompt() {
  const checkboxes = document.querySelectorAll('input[name="domain_chk"]:checked');
  const formData = new FormData();
  checkboxes.forEach((c) => formData.append('domains', c.value));
  formData.append('csrf_token', _llmCsrfToken());

  const res = await fetch('/llm/exchange/export', {
    method: 'POST',
    headers: { 'X-CSRF-Token': _llmCsrfToken() },
    body: formData,
  });
  const data = await res.json();
  if (data.prompt) {
    const area = document.getElementById('prompt-preview');
    area.value = data.prompt;
    navigator.clipboard.writeText(data.prompt);
    const status = document.getElementById('copy-status');
    status.classList.remove('hidden');
    setTimeout(() => status.classList.add('hidden'), 3000);
  }
}

async function parseAndMatchResponse() {
  const rawText = document.getElementById('raw-response-input').value;
  if (!rawText.trim()) return;

  const formData = new FormData();
  formData.append('raw_response', rawText);
  formData.append('csrf_token', _llmCsrfToken());

  const res = await fetch('/llm/exchange/parse', {
    method: 'POST',
    headers: { 'X-CSRF-Token': _llmCsrfToken() },
    body: formData,
  });
  const data = await res.json();
  if (data.status === 'ok') {
    const container = document.getElementById('parsed-items-container');
    const listBox = document.getElementById('items-list-box');
    container.classList.remove('hidden');
    listBox.innerHTML = '';

    const parsed = data.parsed;
    document.getElementById('confirmed-title').value = parsed.title || 'Сквозной план от Внешней ИИ';
    document.getElementById('confirmed-reasoning').value = parsed.reasoning || '';
    document.getElementById('confirmed-items-json').value = JSON.stringify(parsed.items || []);

    (parsed.items || []).forEach((it) => {
      const row = document.createElement('div');
      row.className = 'p-3 bg-archive-950 border border-archive-800 rounded-lg text-xs flex flex-col gap-2';
      row.innerHTML = `
                <div class="font-semibold text-archive-100 flex items-center justify-between">
                    <span>${it.title || 'Активность'}</span>
                    <span class="text-archive-400 text-[10px]">${it.domain || 'general'}</span>
                </div>
                <div class="text-archive-300">${it.notes || ''}</div>
            `;
      listBox.appendChild(row);
    });
  }
}
