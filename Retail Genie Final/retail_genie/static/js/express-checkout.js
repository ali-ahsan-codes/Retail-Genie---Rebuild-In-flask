(() => {
  const heading = document.querySelector('[data-express-products-url]');
  const store = document.getElementById('store');
  if (!heading || !store) return;

  const results = document.getElementById('product-results');
  const cartBody = document.getElementById('cart');
  const payments = document.getElementById('payments');
  const search = document.getElementById('sku-search');
  const idKey = document.getElementById('idempotency-key');
  const csrf = document.querySelector('input[name="csrf_token"]')?.value || '';
  let cart = [];

  const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const money = value => Number(value || 0);
  idKey.value = newKey();

  function renderCart() {
    cartBody.replaceChildren();
    let total = 0;
    cart.forEach((item, index) => {
      const tr = document.createElement('tr');
      const subtotal = money(item.price) * item.quantity;
      total += subtotal;
      [item.sku || item.barcode || '—', item.name, `OMR ${money(item.price).toFixed(3)}`].forEach(value => {
        const td = document.createElement('td');
        td.textContent = value;
        tr.appendChild(td);
      });
      const qtyCell = document.createElement('td');
      const qty = document.createElement('input');
      qty.type = 'number';
      qty.min = '1';
      qty.step = '1';
      qty.value = item.quantity;
      qty.className = 'form-control';
      qty.setAttribute('aria-label', `Quantity for ${item.name}`);
      qty.addEventListener('change', () => {
        item.quantity = Math.max(1, parseInt(qty.value || '1', 10));
        idKey.value = newKey();
        renderCart();
      });
      qtyCell.appendChild(qty);
      tr.appendChild(qtyCell);
      const sum = document.createElement('td');
      sum.textContent = `OMR ${subtotal.toFixed(3)}`;
      tr.appendChild(sum);
      const action = document.createElement('td');
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'button button-quiet';
      remove.textContent = 'Remove';
      remove.addEventListener('click', () => {
        cart.splice(index, 1);
        idKey.value = newKey();
        renderCart();
      });
      action.appendChild(remove);
      tr.appendChild(action);
      cartBody.appendChild(tr);
    });
    document.getElementById('checkout-total').textContent = `Estimated total: OMR ${total.toFixed(3)} (before applicable tax/discount)`;
  }

  function addPayment() {
    const row = document.createElement('div');
    row.className = 'form-grid payment-row';
    row.innerHTML = '<div class="form-field"><label>Tender</label><select class="form-control method"><option value="cash">Cash</option><option value="bank">Bank</option><option value="bank_transfer">Bank Transfer</option><option value="other">Other</option></select></div><div class="form-field"><label>Amount (OMR)</label><input class="form-control amount" type="number" min="0.001" step="0.001" required></div><div class="form-field"><label>Reference (optional)</label><input class="form-control reference" maxlength="128"></div><div><button type="button" class="button button-quiet remove-payment">Remove</button></div>';
    row.querySelector('.remove-payment').addEventListener('click', () => row.remove());
    payments.appendChild(row);
  }

  addPayment();
  document.getElementById('add-payment').addEventListener('click', addPayment);

  let timer;
  const addProduct = product => {
    const found = cart.find(row => row.id === product.id);
    if (found) found.quantity += 1;
    else cart.push({ ...product, quantity: 1 });
    idKey.value = newKey();
    search.value = '';
    results.replaceChildren();
    renderCart();
  };

  async function searchProducts({ scanExact = false } = {}) {
    const term = search.value.trim();
    if (!term) {
      results.replaceChildren();
      return;
    }
    try {
      const url = new URL(heading.dataset.expressProductsUrl, location.origin);
      url.searchParams.set('store_id', store.value);
      url.searchParams.set('q', term);
      const response = await fetch(url, { cache: 'no-store', credentials: 'same-origin' });
      if (!response.ok) return;
      const data = await response.json();
      const products = data.products || [];
      const normalized = term.toLocaleUpperCase();
      const exact = products.find(product => [product.sku, product.barcode].some(value => String(value || '').trim().toLocaleUpperCase() === normalized));
      if (scanExact && exact) {
        if (!exact.price || Number(exact.quantity_on_hand) < 1) {
          results.textContent = 'This product has no sellable stock at the selected store.';
          return;
        }
        addProduct(exact);
        return;
      }
      results.replaceChildren();
      products.forEach(product => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'button button-secondary';
        button.textContent = `${product.sku || product.barcode || ''} · ${product.name} · OMR ${product.price == null ? '—' : money(product.price).toFixed(3)} · Stock ${product.quantity_on_hand}`;
        button.disabled = !product.price || product.quantity_on_hand < 1;
        button.addEventListener('click', () => addProduct(product));
        results.appendChild(button);
      });
      if (scanExact && !exact) results.textContent = `No exact SKU/barcode match for “${term}”. Choose a result or check the code.`;
    } catch (_error) {
      results.textContent = 'Product search is temporarily unavailable.';
    }
  }

  search.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => void searchProducts(), 180);
  });
  search.addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    clearTimeout(timer);
    void searchProducts({ scanExact: true });
  });

  store.addEventListener('change', () => {
    cart = [];
    idKey.value = newKey();
    renderCart();
    results.replaceChildren();
  });

  document.getElementById('complete-checkout').addEventListener('click', async () => {
    const result = document.getElementById('result');
    result.textContent = 'Processing…';
    if (!cart.length) {
      result.textContent = 'Add products to the cart first.';
      return;
    }
    const tenderRows = [...payments.querySelectorAll('.payment-row')];
    const payload = {
      store_id: store.value,
      customer_phone: document.getElementById('customer-phone').value,
      customer_name: document.getElementById('customer-name').value,
      items: cart.map(row => ({ sku: row.sku, quantity: row.quantity })),
      payments: tenderRows.map(row => ({
        method: row.querySelector('.method').value,
        amount: row.querySelector('.amount').value,
        transaction_reference: row.querySelector('.reference').value,
      })),
      idempotency_key: idKey.value,
    };
    try {
      const response = await fetch(heading.dataset.expressCheckoutUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        result.textContent = data.message || 'Checkout failed.';
        return;
      }
      result.textContent = `${data.replayed ? 'Already processed: ' : 'Sale complete: '}${data.order.order_number} · ${data.order.invoice_number || ''} · OMR ${money(data.order.total_amount).toFixed(3)}`;
      const printLink = document.getElementById('print-receipt');
      if (printLink) {
        printLink.href = `/sales/orders/${encodeURIComponent(data.order.id)}/print?company_id=${encodeURIComponent(data.order.company_id)}`;
        printLink.hidden = false;
      }
      cart = [];
      renderCart();
      idKey.value = newKey();
    } catch (_error) {
      result.textContent = 'Checkout could not be reached. Retry with the same checkout key.';
    }
  });
})();
