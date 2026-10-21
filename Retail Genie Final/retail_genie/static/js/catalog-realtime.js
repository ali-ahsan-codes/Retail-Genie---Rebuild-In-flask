(() => {
  const panel = document.querySelector("[data-realtime-store]");
  if (!panel || typeof window.io !== "function") return;

  const storeId = panel.dataset.realtimeStore;
  const tenantId = panel.dataset.tenantContainer;
  const status = panel.querySelector("[data-realtime-status]");
  if (!storeId) return;

  const cursorKey = `retail-genie:inventory:${tenantId}:${storeId}`;
  let cursor = Number(panel.dataset.realtimeCursor || 0);
  try {
    const savedCursor = Number(window.sessionStorage.getItem(cursorKey) || 0);
    if (Number.isSafeInteger(savedCursor) && savedCursor > cursor) cursor = savedCursor;
  } catch (_error) {
    // Storage can be disabled; the server-rendered cursor and replay still work.
  }

  let cursorHint = cursor;
  let connectionGeneration = 0;
  let syncGeneration = -1;
  let syncAgain = false;
  let syncPromise = null;
  let activeController = null;
  let retryTimer = null;
  let subscribed = false;
  let accessRevoked = false;

  const setStatus = (message, isError = false) => {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-error", isError);
  };

  const rememberCursor = () => {
    try {
      window.sessionStorage.setItem(cursorKey, String(cursor));
    } catch (_error) {
      // Do not interrupt live updates when browser storage is unavailable.
    }
  };

  const applyReplayedEvent = (event) => {
    if (!event || !Number.isSafeInteger(Number(event.id)) || Number(event.id) <= cursor) return;
    const eventId = Number(event.id);
    const data = event.data || {};
    const productId = String(data.product_id || "");
    if (productId) {
      const row = Array.from(panel.querySelectorAll("[data-product-id]")).find(
        (candidate) => candidate.dataset.productId === productId,
      );
      const stockCell = row && row.querySelector("[data-stock-value]");
      if (stockCell && Number.isFinite(Number(data.quantity_on_hand))) {
        stockCell.textContent = String(data.quantity_on_hand);
        if (Object.prototype.hasOwnProperty.call(data, "low_stock_threshold")) {
          stockCell.dataset.lowStockThreshold = data.low_stock_threshold == null
            ? ""
            : String(data.low_stock_threshold);
        }
        const thresholdText = stockCell.dataset.lowStockThreshold || "";
        const threshold = thresholdText === "" ? null : Number(thresholdText);
        const isLow = threshold !== null && Number(data.quantity_on_hand) <= threshold;
        let warning = stockCell.querySelector(".stock-warning");
        if (isLow && !warning) {
          warning = document.createElement("small");
          warning.className = "stock-warning";
          warning.textContent = "Low stock";
          stockCell.appendChild(warning);
        } else if (!isLow && warning) {
          warning.remove();
        }
      }
    }
    cursor = eventId;
    rememberCursor();
  };

  const replayMissedEvents = async (generation, signal) => {
    let replayAgain = true;
    while (replayAgain && generation === connectionGeneration && !signal.aborted) {
      replayAgain = false;
      const cursorAtPassStart = cursor;
      let hasMore = true;
      while (hasMore && generation === connectionGeneration && !signal.aborted) {
        const query = new URLSearchParams({ store_id: storeId, after_id: String(cursor) });
        const response = await fetch(`/api/v1/realtime/events?${query.toString()}`, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal,
        });
        if (response.status === 401 || response.status === 403) {
          const error = new Error("Realtime access was denied");
          error.accessRevoked = true;
          throw error;
        }
        if (!response.ok) throw new Error("Event replay failed");
        const result = await response.json();
        (result.events || []).forEach(applyReplayedEvent);
        const nextCursor = Number(result.next_cursor || cursor);
        if (Number.isSafeInteger(nextCursor) && nextCursor > cursor) {
          cursor = nextCursor;
          rememberCursor();
        }
        hasMore = Boolean(result.has_more);
      }
      const announcedGap = cursorHint > cursor;
      if (announcedGap && cursor <= cursorAtPassStart) {
        throw new Error("The replay feed did not reach its announced cursor");
      }
      if (announcedGap || syncAgain) replayAgain = true;
      syncAgain = false;
    }
  };

  const startReplay = (generation) => {
    if (generation !== connectionGeneration || !socket.connected || !subscribed || accessRevoked) return;
    if (syncPromise && syncGeneration === generation) {
      syncAgain = true;
      return syncPromise;
    }

    const controller = new AbortController();
    activeController = controller;
    syncGeneration = generation;
    syncAgain = false;
    setStatus("Synchronizing live inventory…");

    const task = replayMissedEvents(generation, controller.signal)
      .then(() => {
        if (generation === connectionGeneration && socket.connected && !accessRevoked) {
          setStatus("Live inventory connected");
        }
      })
      .catch((error) => {
        if (generation !== connectionGeneration || error.name === "AbortError") return;
        syncAgain = false;
        if (error.accessRevoked) {
          accessRevoked = true;
          setStatus("Live updates unavailable: access changed. Reload the page.", true);
          socket.disconnect();
          return;
        }
        setStatus("Live connection active; retrying missed updates…", true);
        window.clearTimeout(retryTimer);
        retryTimer = window.setTimeout(() => startReplay(generation), 2000);
      })
      .finally(() => {
        if (generation !== connectionGeneration) return;
        if (activeController === controller) activeController = null;
        const shouldReplayAgain = syncAgain && !accessRevoked;
        syncAgain = false;
        syncPromise = null;
        if (shouldReplayAgain && socket.connected) {
          window.queueMicrotask(() => startReplay(generation));
        }
      });
    syncPromise = task;
    return task;
  };

  const socket = window.io("/retail", { withCredentials: true });
  socket.on("connect", () => {
    connectionGeneration += 1;
    const generation = connectionGeneration;
    subscribed = false;
    accessRevoked = false;
    syncAgain = false;
    cursorHint = cursor;
    window.clearTimeout(retryTimer);
    if (activeController) activeController.abort();
    activeController = null;
    setStatus("Connecting to live inventory…");

    socket.emit("subscribe_store", { store_id: storeId }, (ack) => {
      if (generation !== connectionGeneration) return;
      if (!ack || !ack.ok) {
        accessRevoked = true;
        setStatus("Live updates are not authorized for this store.", true);
        socket.disconnect();
        return;
      }
      subscribed = true;
      const acknowledgedCursor = Number(ack.cursor || 0);
      if (Number.isSafeInteger(acknowledgedCursor) && acknowledgedCursor > cursorHint) {
        cursorHint = acknowledgedCursor;
      }
      startReplay(generation);
    });
  });

  // Pushes are wake-up signals, not the source of cursor advancement: replaying
  // the durable feed in order prevents a fast later push from skipping events.
  socket.onAny((eventName, event) => {
    if (eventName === "access.revoked") {
      accessRevoked = true;
      setStatus("Live access changed. Reload to refresh permissions.", true);
      socket.disconnect();
      return;
    }
    const eventId = Number(event && event.id);
    if (!Number.isSafeInteger(eventId) || eventId <= cursor) return;
    if (eventId > cursorHint) cursorHint = eventId;
    if (subscribed) startReplay(connectionGeneration);
  });

  socket.on("disconnect", () => {
    connectionGeneration += 1;
    subscribed = false;
    syncAgain = false;
    window.clearTimeout(retryTimer);
    if (activeController) activeController.abort();
    activeController = null;
    setStatus("Live inventory disconnected; reconnecting…", true);
  });

  socket.on("connect_error", () => setStatus("Live inventory unavailable; reconnecting…", true));
})();
