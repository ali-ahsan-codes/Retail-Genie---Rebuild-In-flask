(() => {
  const app = document.getElementById('cashup-app');
  if (!app) return;
  const list = document.getElementById('cashup-list');
  const message = document.getElementById('cashup-message');
  const csrf = document.getElementById('cashup-csrf-token')?.value || '';
  const companyId = app.dataset.companyId || '';
  const canReview = app.dataset.canReview === 'true';
  const storeSelect = document.getElementById('cashup-store-id');
  const filter = document.getElementById('cashup-filter-store');

  async function api(url, method = 'GET', body = null) {
    const headers = { Accept: 'application/json' };
    const options = { method, headers, credentials: 'same-origin' };
    if (body) {
      headers['Content-Type'] = 'application/json';
      headers['X-CSRFToken'] = csrf;
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || 'Request failed.');
    return data;
  }

  function setMessage(text, error = false) {
    message.textContent = text;
    message.className = `approval-message ${error ? 'is-error' : 'is-success'}`;
  }

  function addText(parent, tag, text, className = '') {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    parent.append(element);
    return element;
  }

  function render(rows) {
    list.replaceChildren();
    if (!rows.length) {
      addText(list, 'p', 'No closeouts found.', 'empty-state');
      return;
    }
    rows.forEach((row) => {
      const card = document.createElement('article');
      card.className = 'cashup-entry';
      const heading = document.createElement('div');
      heading.className = 'approval-request-heading';
      addText(heading, 'strong', `${row.store_id} · ${row.business_date}`);
      const status = addText(heading, 'span', row.status.replace('_', ' '), `status-pill status-${row.status}`);
      status.setAttribute('aria-label', `Status: ${row.status}`);
      card.append(heading);
      const table = document.createElement('div');
      table.className = 'cashup-values';
      ['cash', 'bank', 'bank_transfer', 'other'].forEach((method) => {
        const rowEl = document.createElement('div');
        rowEl.className = 'cashup-value-row';
        addText(rowEl, 'span', method.replace('_', ' '));
        addText(rowEl, 'span', `Expected OMR ${row.expected[method]}`);
        addText(rowEl, 'span', `Counted OMR ${row.counted[method]}`);
        addText(rowEl, 'strong', `Variance OMR ${row.variance[method]}`);
        table.append(rowEl);
      });
      card.append(table);
      if (row.notes) addText(card, 'p', `Manager notes: ${row.notes}`, 'cashup-notes');
      if (row.review_note) addText(card, 'p', `Review note: ${row.review_note}`, 'cashup-notes');
      if (canReview && row.status === 'submitted') {
        const actions = document.createElement('div');
        actions.className = 'approval-actions';
        const approve = document.createElement('button');
        approve.type = 'button';
        approve.className = 'button button-primary';
        approve.textContent = 'Approve';
        approve.addEventListener('click', () => review(row.id, 'approve'));
        const reject = document.createElement('button');
        reject.type = 'button';
        reject.className = 'button button-danger';
        reject.textContent = 'Reject';
        reject.addEventListener('click', () => review(row.id, 'reject'));
        actions.append(approve, reject);
        card.append(actions);
      }
      list.append(card);
    });
  }

  async function load() {
    list.replaceChildren();
    addText(list, 'p', 'Loading closeouts…', 'empty-state');
    const params = new URLSearchParams();
    if (companyId) params.set('company_id', companyId);
    if (canReview && filter?.value) params.set('store_id', filter.value);
    try {
      const data = await api(`/api/v1/cashups?${params.toString()}`);
      render(data.cashups || []);
    } catch (error) {
      render([]);
      setMessage(error.message, true);
    }
  }

  async function submit() {
    const counted = {
      cash: document.getElementById('counted-cash').value,
      bank: document.getElementById('counted-bank').value,
      bank_transfer: document.getElementById('counted-bank_transfer').value,
      other: document.getElementById('counted-other').value,
    };
    try {
      const data = await api('/api/v1/cashups', 'POST', {
        company_id: companyId || undefined,
        store_id: storeSelect.value,
        business_date: document.getElementById('cashup-date').value,
        counted,
        notes: document.getElementById('cashup-notes').value,
      });
      const expected = data.cashup.expected;
      const variance = data.cashup.variance;
      setMessage(`Submitted for approval. Cash expected OMR ${expected.cash} (variance ${variance.cash}); bank expected OMR ${expected.bank} (variance ${variance.bank}).`);
      await load();
    } catch (error) {
      setMessage(error.message, true);
    }
  }

  async function review(id, decision) {
    let note = '';
    if (decision === 'reject') {
      const response = window.prompt('Why is this closeout being rejected?', '');
      if (response === null) return;
      note = response;
    } else if (!window.confirm('Approve this daily cash / bank closeout?')) {
      return;
    }
    try {
      await api(`/api/v1/cashups/${encodeURIComponent(id)}/review`, 'POST', { decision, note });
      setMessage(`Closeout ${decision}d.`);
      await load();
    } catch (error) {
      setMessage(error.message, true);
    }
  }

  document.getElementById('submit-cashup').addEventListener('click', submit);
  document.getElementById('refresh-cashups').addEventListener('click', load);
  filter?.addEventListener('change', load);
  load();
})();
