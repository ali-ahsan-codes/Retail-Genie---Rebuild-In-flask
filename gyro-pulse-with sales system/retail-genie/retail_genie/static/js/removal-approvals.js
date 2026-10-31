(() => {
  const app = document.getElementById('removal-approvals-app');
  if (!app) return;
  const list = document.getElementById('removal-approval-list');
  const message = document.getElementById('removal-approval-message');
  const companyId = app.dataset.companyId || '';
  const csrf = document.getElementById('approval-csrf-token')?.value || '';
  const store = document.getElementById('approval-store-id');

  async function request(url, method = 'GET', body = null) {
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

  function render(rows) {
    list.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = 'No pending removal requests.';
      list.append(empty);
      return;
    }
    rows.forEach((row) => {
      const card = document.createElement('article');
      card.className = 'approval-request';
      const heading = document.createElement('div');
      heading.className = 'approval-request-heading';
      const title = document.createElement('strong');
      title.textContent = `${row.item_name} · ${row.quantity_to_remove} requested`;
      const badge = document.createElement('span');
      badge.className = 'pill pill-muted';
      badge.textContent = row.store_id;
      heading.append(title, badge);
      const detail = document.createElement('p');
      detail.textContent = `${row.customer_name || 'Customer'} · ${row.customer_phone} · ${row.business_date || ''}`;
      const reason = document.createElement('p');
      reason.className = 'approval-reason';
      reason.textContent = `Reason: ${row.reason}`;
      const meta = document.createElement('p');
      meta.className = 'muted small-copy';
      meta.textContent = `Bill ${row.order_id} · requested by ${row.requested_by_id}`;
      const actions = document.createElement('div');
      actions.className = 'approval-actions';
      const approve = document.createElement('button');
      approve.type = 'button';
      approve.className = 'button button-primary';
      approve.textContent = 'Approve removal';
      approve.addEventListener('click', () => review(row.id, 'approve'));
      const reject = document.createElement('button');
      reject.type = 'button';
      reject.className = 'button button-danger';
      reject.textContent = 'Reject';
      reject.addEventListener('click', () => review(row.id, 'reject'));
      actions.append(approve, reject);
      card.append(heading, detail, reason, meta, actions);
      list.append(card);
    });
  }

  async function load() {
    list.replaceChildren();
    const loading = document.createElement('p');
    loading.className = 'empty-state';
    loading.textContent = 'Loading requests…';
    list.append(loading);
    const params = new URLSearchParams();
    if (companyId) params.set('company_id', companyId);
    if (store.value) params.set('store_id', store.value);
    try {
      const data = await request(`/api/v1/order-removal-requests?${params.toString()}`);
      render(data.removal_requests || []);
      setMessage('Approval list is up to date.');
    } catch (error) {
      render([]);
      setMessage(error.message, true);
    }
  }

  async function review(id, decision) {
    let reviewReason = '';
    if (decision === 'reject') {
      const value = window.prompt('Why is this removal request being rejected?', '');
      if (value === null) return;
      reviewReason = value;
    } else if (!window.confirm('Approve this audited item-removal request?')) {
      return;
    }
    try {
      await request(`/api/v1/order-removal-requests/${encodeURIComponent(id)}/review`, 'POST', { decision, review_reason: reviewReason });
      setMessage(`Request ${decision}d. The order and audit trail have been updated.`);
      await load();
    } catch (error) {
      setMessage(error.message, true);
    }
  }

  document.getElementById('refresh-removals').addEventListener('click', load);
  store.addEventListener('change', load);
  load();
})();
