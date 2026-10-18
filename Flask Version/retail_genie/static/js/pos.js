(() => {
  const app = document.getElementById('pos-app');
  if (!app) return;

  const $ = (selector) => document.querySelector(selector);
  const storeSelect = $('#store-id');
  const phoneInput = $('#phone-number');
  const messages = $('#pos-message');
  const results = $('#order-results');
  const selectedCard = $('#selected-order-card');
  const newProductSelect = $('#new-item-product');
  const addProductSelect = $('#add-item-product');
  const csrfToken = $('#csrf-token')?.value || '';
  const companyId = app.dataset.companyId || '';
  let selectedOrderId = null;
  let pendingPaymentKey = null;
  let catalogProducts = [];

  function message(text, kind = 'info') {
    messages.textContent = text;
    messages.className = `flash-stack pos-message pos-message-${kind}`;
  }

  async function api(url, method = 'GET', payload = null) {
    const headers = { Accept: 'application/json' };
    const options = { method, headers, credentials: 'same-origin' };
    if (payload !== null) {
      headers['Content-Type'] = 'application/json';
      headers['X-CSRFToken'] = csrfToken;
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(url, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || 'The request could not be completed.');
    return body;
  }

  function companyQuery() {
    return companyId ? `&company_id=${encodeURIComponent(companyId)}` : '';
  }

  function updateProductSummary(select, summary) {
    if (!select || !summary) return;
    const product = catalogProducts.find((row) => row.id === select.value);
    summary.textContent = product
      ? `Price OMR ${product.price ?? 'not set'} · ${product.stock_quantity === null ? 'stock visibility restricted' : `on hand ${product.stock_quantity}`}`
      : 'Choose a product to see its current price and stock.';
  }

  function renderProductOptions(select, summary) {
    if (!select) return;
    select.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = catalogProducts.length ? 'Choose a product…' : 'No products available';
    select.append(placeholder);
    for (const product of catalogProducts) {
      const option = document.createElement('option');
      option.value = product.id;
      const stockText = product.stock_quantity === null ? 'stock restricted' : `stock ${product.stock_quantity}`;
      option.textContent = `${product.sku ? `${product.sku} · ` : ''}${product.name} · OMR ${product.price ?? '—'} · ${stockText}`;
      option.disabled = !product.price || Number(product.price) <= 0 || (product.stock_quantity !== null && Number(product.stock_quantity) <= 0);
      select.append(option);
    }
    updateProductSummary(select, summary);
  }

  async function loadCatalog() {
    if (!storeSelect?.value) return;
    if (newProductSelect) newProductSelect.disabled = true;
    if (addProductSelect) addProductSelect.disabled = true;
    const query = new URLSearchParams({ store_id: storeSelect.value });
    if (companyId) query.set('company_id', companyId);
    try {
      const body = await api(`/api/v1/products?${query.toString()}`);
      catalogProducts = body.products || [];
      renderProductOptions(newProductSelect, $('#new-product-stock'));
      renderProductOptions(addProductSelect, $('#add-product-stock'));
      if (newProductSelect) newProductSelect.disabled = !catalogProducts.length;
      if (addProductSelect) addProductSelect.disabled = !catalogProducts.length;
    } catch (error) {
      catalogProducts = [];
      renderProductOptions(newProductSelect, $('#new-product-stock'));
      renderProductOptions(addProductSelect, $('#add-product-stock'));
      const messageOption = `Catalog unavailable: ${error.message}`;
      for (const select of [newProductSelect, addProductSelect]) {
        if (!select) continue;
        select.replaceChildren();
        const option = document.createElement('option');
        option.value = '';
        option.textContent = messageOption;
        select.append(option);
        select.disabled = true;
      }
      message(error.message, 'error');
    }
  }

  function clearResults(text) {
    results.replaceChildren();
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = text;
    results.append(empty);
  }

  function renderOrders(orders) {
    results.replaceChildren();
    if (!orders.length) {
      clearResults('No open bills found for this phone number. Create a bill on the right.');
      return;
    }
    for (const order of orders) {
      const card = document.createElement('article');
      card.className = 'order-result';
      const heading = document.createElement('div');
      heading.className = 'order-result-heading';
      const customer = document.createElement('strong');
      customer.textContent = order.customer_name || order.customer_phone;
      const date = document.createElement('span');
      date.className = 'pill pill-muted';
      date.textContent = order.business_date;
      heading.append(customer, date);
      const details = document.createElement('p');
      details.className = 'muted';
      details.textContent = `${order.order_number || order.id} · ${order.items.length} item${order.items.length === 1 ? '' : 's'} · ${order.origin_store_id} · Balance OMR ${order.balance}`;
      const button = document.createElement('button');
      button.className = 'button button-secondary button-full';
      button.type = 'button';
      button.textContent = 'Continue this bill';
      button.addEventListener('click', () => loadOrder(order.id));
      card.append(heading, details, button);
      results.append(card);
    }
  }

  async function lookup({ keepSelected = false } = {}) {
    const phone = phoneInput.value.trim();
    if (!phone) {
      message('Enter a customer phone number to find an open bill.', 'error');
      phoneInput.focus();
      return;
    }
    message('Searching this company for open bills…');
    if (!keepSelected) {
      selectedCard.hidden = true;
      selectedOrderId = null;
    }
    const query = new URLSearchParams({ store_id: storeSelect.value, phone });
    if (companyId) query.set('company_id', companyId);
    try {
      const body = await api(`/api/v1/orders/open?${query.toString()}`);
      renderOrders(body.orders || []);
      message(`${(body.orders || []).length} open bill${body.orders?.length === 1 ? '' : 's'} found.`, 'success');
    } catch (error) {
      clearResults('Search could not be completed.');
      message(error.message, 'error');
    }
  }

  async function loadOrder(orderId) {
    const query = new URLSearchParams({ store_id: storeSelect.value });
    try {
      const body = await api(`/api/v1/orders/${encodeURIComponent(orderId)}?${query.toString()}`);
      selectedOrderId = orderId;
      renderSelected(body.order);
      message('Bill loaded. It remains open until the full balance is paid.', 'success');
      selectedCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      message(error.message, 'error');
      selectedCard.hidden = true;
      selectedOrderId = null;
    }
  }

  function renderSelected(order) {
    selectedCard.hidden = false;
    $('#selected-order-title').textContent = order.customer_name || order.customer_phone;
    $('#selected-order-summary').textContent = `Order ${order.order_number || order.id} · ${order.business_date} · opened at ${order.origin_store_id}`;
    $('#order-total').textContent = `OMR ${order.total_amount}`;
    $('#order-paid').textContent = `OMR ${order.paid_amount}`;
    $('#order-balance').textContent = `OMR ${order.balance}`;
    $('#payment-amount').value = Number(order.balance) > 0 ? order.balance : '';
    const list = $('#selected-order-items');
    list.replaceChildren();
    if (!order.items.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = 'No active items.';
      list.append(empty);
    }
    for (const item of order.items) {
      const row = document.createElement('div');
      row.className = 'order-item-row';
      const label = document.createElement('div');
      const name = document.createElement('strong');
      name.textContent = item.name;
      const meta = document.createElement('span');
      meta.className = 'muted';
      meta.textContent = `${item.quantity} × OMR ${item.unit_price} · Added at ${item.added_store_id}`;
      label.append(name, meta);
      const total = document.createElement('strong');
      total.textContent = `OMR ${item.line_total}`;
      row.append(label, total);
      const remove = document.createElement('button');
      remove.className = 'text-button';
      remove.type = 'button';
      remove.textContent = 'Request item removal';
      remove.addEventListener('click', () => requestRemoval(order.id, item));
      row.append(remove);
      list.append(row);
    }
    const paidList = document.createElement('div');
    paidList.className = 'payment-history';
    for (const payment of order.payments) {
      const row = document.createElement('p');
      row.textContent = `${payment.method.replace('_', ' ')} · OMR ${payment.amount} · ${payment.created_at || ''}`;
      paidList.append(row);
    }
    if (order.payments.length) list.append(paidList);
    const isOpen = order.status === 'open';
    $('#add-item-button').disabled = !isOpen;
    $('#payment-button').disabled = !isOpen || Number(order.balance) <= 0;
    if (order.status !== 'open') {
      const invoice = document.createElement('p');
      invoice.className = 'approval-note';
      invoice.textContent = order.invoice_number ? `Settled · ${order.invoice_category} invoice ${order.invoice_number}` : `Bill status: ${order.status}`;
      list.append(invoice);
    }
  }

  async function createOrder() {
    const phone = phoneInput.value.trim();
    const productId = newProductSelect?.value || '';
    const quantity = Number($('#new-item-quantity').value);
    if (!phone || !productId || !Number.isInteger(quantity) || quantity < 1) {
      message('Enter a phone number, choose a catalog product, and enter a whole-number quantity.', 'error');
      return;
    }
    const payload = {
      store_id: storeSelect.value,
      company_id: companyId || undefined,
      customer_phone: phone,
      customer_name: $('#customer-name').value.trim() || undefined,
      items: [{ product_id: productId, quantity }],
    };
    try {
      const body = await api('/api/v1/orders', 'POST', payload);
      const createdOrderId = body.order.id;
      selectedOrderId = createdOrderId;
      renderSelected(body.order);
      message(`Open bill ${body.order.order_number || ''} created; inventory was updated.`, 'success');
      await Promise.all([loadCatalog(), lookup({ keepSelected: true })]);
      await loadOrder(createdOrderId);
    } catch (error) {
      message(error.message, 'error');
    }
  }

  async function addItem() {
    if (!selectedOrderId) return;
    const productId = addProductSelect?.value || '';
    const quantity = Number($('#add-item-quantity').value);
    if (!productId || !Number.isInteger(quantity) || quantity < 1) {
      message('Choose a catalog product and enter a whole-number quantity.', 'error');
      return;
    }
    try {
      const body = await api(`/api/v1/orders/${encodeURIComponent(selectedOrderId)}/items`, 'POST', {
        store_id: storeSelect.value,
        product_id: productId,
        quantity,
      });
      const updatedOrderId = body.order.id;
      renderSelected(body.order);
      addProductSelect.value = '';
      $('#add-item-quantity').value = '1';
      message('Product added to the open bill and stock deducted.', 'success');
      await Promise.all([loadCatalog(), lookup({ keepSelected: true })]);
      await loadOrder(updatedOrderId);
    } catch (error) {
      message(error.message, 'error');
    }
  }

  async function requestRemoval(orderId, item) {
    const quantityText = window.prompt(`How many of “${item.name}” should be removed? (1–${item.quantity})`, '1');
    if (quantityText === null) return;
    const reason = window.prompt('Reason for removal (manager approval required):', '');
    if (reason === null) return;
    try {
      await api(`/api/v1/orders/${encodeURIComponent(orderId)}/items/${encodeURIComponent(item.id)}/removal-requests`, 'POST', {
        store_id: storeSelect.value,
        quantity_to_remove: quantityText,
        reason,
      });
      message('Removal request sent for manager approval and added to the audit trail.', 'success');
    } catch (error) {
      message(error.message, 'error');
    }
  }

  async function makePayment() {
    if (!selectedOrderId) return;
    const amount = $('#payment-amount').value;
    if (!amount) {
      message('Enter a payment amount.', 'error');
      return;
    }
    if (!pendingPaymentKey) pendingPaymentKey = (window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);
    try {
      const body = await api(`/api/v1/orders/${encodeURIComponent(selectedOrderId)}/payments`, 'POST', {
        store_id: storeSelect.value,
        method: $('#payment-method').value,
        amount,
        idempotency_key: pendingPaymentKey,
      });
      pendingPaymentKey = null;
      const paidOrderId = body.order.id;
      renderSelected(body.order);
      const invoice = body.order.invoice_number ? ` Invoice ${body.order.invoice_number}.` : '';
      message(body.replayed ? 'This payment was already recorded.' : `Payment recorded.${invoice}`, 'success');
      await lookup({ keepSelected: true });
      await loadOrder(paidOrderId);
    } catch (error) {
      message(error.message, 'error');
    }
  }

  $('#lookup-button').addEventListener('click', lookup);
  $('#create-order-button').addEventListener('click', createOrder);
  $('#add-item-button').addEventListener('click', addItem);
  $('#payment-button').addEventListener('click', makePayment);
  phoneInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') lookup(); });
  newProductSelect?.addEventListener('change', () => updateProductSummary(newProductSelect, $('#new-product-stock')));
  addProductSelect?.addEventListener('change', () => updateProductSummary(addProductSelect, $('#add-product-stock')));
  storeSelect.addEventListener('change', () => {
    selectedCard.hidden = true;
    selectedOrderId = null;
    clearResults('Search a phone number to see open bills.');
    void loadCatalog();
  });
  void loadCatalog();
})();
