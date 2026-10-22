(() => {
  const root = document.querySelector("[data-stock-adjust-store]");
  if (!root || !root.dataset.stockAdjustStore || !root.dataset.userId || !root.dataset.tenantContainer) return;

  const userId = root.dataset.userId;
  const tenantId = root.dataset.tenantContainer;
  const storeId = root.dataset.stockAdjustStore;
  const forms = [...document.querySelectorAll("form.stock-adjust-form[data-api-url]")];
  if (!forms.length || !("indexedDB" in window)) return;

  const openDb = () => new Promise((resolve, reject) => {
    const request = indexedDB.open("retail-genie-stock-outbox-v1", 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("operations")) {
        request.result.createObjectStore("operations", { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  const withStore = async (mode, callback) => {
    const database = await openDb();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = database.transaction("operations", mode);
        const store = transaction.objectStore("operations");
        const result = callback(store);
        transaction.oncomplete = () => resolve(result);
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error || new Error("Outbox transaction aborted"));
      });
    } finally {
      database.close();
    }
  };

  const getAll = () => withStore("readonly", store => {
    const request = store.getAll();
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  });
  const save = operation => withStore("readwrite", store => store.put(operation));
  const remove = key => withStore("readwrite", store => store.delete(key));

  const makeKey = () => {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
  };

  const formFor = operation => forms.find(form => form.dataset.apiUrl === operation.apiUrl);
  const setStatus = (operation, text, blocked = false) => {
    const form = formFor(operation);
    const target = form && form.querySelector(".stock-sync-status");
    if (!target) return;
    target.textContent = text;
    target.classList.toggle("is-blocked", blocked);
    let discard = form.querySelector("[data-discard-stock-operation]");
    if (blocked && !discard) {
      discard = document.createElement("button");
      discard.type = "button";
      discard.className = "link-button stock-outbox-discard";
      discard.dataset.discardStockOperation = operation.key;
      discard.textContent = "Discard queued update";
      target.after(discard);
    } else if (!blocked && discard) {
      discard.remove();
    }
  };

  const csrfToken = form => form.querySelector('input[name="csrf_token"]')?.value || "";
  const submit = async operation => {
    const form = formFor(operation);
    if (!form) return "deferred";
    try {
      const response = await fetch(operation.apiUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(form),
        },
        body: JSON.stringify({
          store_id: operation.storeId,
          quantity_delta: operation.delta,
          reason: operation.reason,
          idempotency_key: operation.key,
        }),
      });
      if (response.ok) {
        await remove(operation.key);
        setStatus(operation, "Stock adjustment synced.");
        return "sent";
      }
      if ([400, 401, 403, 404, 409, 422].includes(response.status)) {
        operation.blocked = true;
        operation.blockedAt = new Date().toISOString();
        await save(operation);
        setStatus(operation, "Not synced: access or validation changed. Review before retrying.", true);
        return "blocked";
      }
    } catch (_error) {
      // A failed fetch is ambiguous: retaining the exact key/body makes retry safe.
    }
    operation.blocked = false;
    await save(operation);
    setStatus(operation, "Saved on this device; waiting for a connection.");
    return "queued";
  };

  const flush = async () => {
    if (!navigator.onLine) return;
    let operations;
    try {
      operations = await getAll();
    } catch (_error) {
      return;
    }
    for (const operation of operations) {
      if (operation.userId !== userId || operation.tenantId !== tenantId || operation.storeId !== storeId || operation.blocked) continue;
      await submit(operation);
    }
  };

  forms.forEach(form => {
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const delta = Number(form.elements.delta.value);
      const reason = String(form.elements.reason.value || "").trim();
      if (!Number.isSafeInteger(delta) || delta === 0 || !reason) {
        form.reportValidity();
        return;
      }
      const operation = {
        key: makeKey(),
        apiUrl: form.dataset.apiUrl,
        userId,
        tenantId,
        storeId,
        productId: form.dataset.apiUrl.split("/").filter(Boolean).at(-2),
        delta,
        reason,
        queuedAt: new Date().toISOString(),
        blocked: false,
      };
      setStatus(operation, "Saving adjustment…");
      try {
        await save(operation);
        const result = await submit(operation);
        if (result === "sent") {
          form.elements.delta.value = "";
          form.elements.reason.value = "";
        }
      } catch (_error) {
        setStatus(operation, "Could not save this update on this device. Keep the page open and try again.", true);
      }
    });
  });

  document.addEventListener("click", async event => {
    const button = event.target.closest("[data-discard-stock-operation]");
    if (!button) return;
    const key = button.dataset.discardStockOperation;
    await remove(key);
    button.remove();
    const status = button.previousElementSibling;
    if (status) status.textContent = "Queued update discarded.";
  });

  window.addEventListener("online", flush);
  flush();
})();
