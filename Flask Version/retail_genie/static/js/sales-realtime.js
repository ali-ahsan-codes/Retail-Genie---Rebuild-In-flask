(() => {
  const notice = document.createElement("aside");
  notice.className = "realtime-change-notice";
  notice.setAttribute("role", "status");
  notice.setAttribute("aria-live", "polite");
  notice.hidden = true;
  const text = document.createElement("span");
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.className = "button button-secondary button-small";
  refresh.textContent = "Refresh view";
  refresh.addEventListener("click", () => window.location.reload());
  notice.append(text, refresh);
  document.querySelector("main.page-shell")?.prepend(notice);

  const showNotice = message => {
    text.textContent = message;
    notice.hidden = false;
  };
  const cursorKey = storeId => `retail-genie:events:${storeId}`;
  const getCursor = storeId => {
    try {
      const value = Number(sessionStorage.getItem(cursorKey(storeId)) || 0);
      return Number.isSafeInteger(value) && value >= 0 ? value : 0;
    } catch (_error) {
      return 0;
    }
  };
  const setCursor = (storeId, value) => {
    try {
      sessionStorage.setItem(cursorKey(storeId), String(value));
    } catch (_error) {
      // Replay remains available from the in-memory cursor during this visit.
    }
  };

  let socket;
  const stores = new Map();
  const replay = async (storeId, generation) => {
    const state = stores.get(storeId);
    if (!state || state.generation !== generation || !socket?.connected) return;
    let afterId = state.cursor;
    try {
      for (;;) {
        const query = new URLSearchParams({ store_id: storeId, after_id: String(afterId) });
        const response = await fetch(`/api/v1/realtime/events?${query}`, {
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (response.status === 410) {
          showNotice("Some updates expired while this page was offline. Refresh to load the latest view.");
          return;
        }
        if (response.status === 401 || response.status === 403) {
          showNotice("Realtime access changed. Refresh to check your current permissions.");
          socket.disconnect();
          return;
        }
        if (!response.ok) throw new Error("Event replay failed");
        const result = await response.json();
        const priorCursor = afterId;
        for (const event of result.events || []) {
          window.dispatchEvent(new CustomEvent("retail-genie:realtime-event", { detail: event }));
          showNotice("New activity is available for this store. Refresh to load the latest view.");
        }
        const nextCursor = Number(result.next_cursor ?? afterId);
        if (Number.isSafeInteger(nextCursor) && nextCursor >= afterId) {
          afterId = nextCursor;
          state.cursor = nextCursor;
          setCursor(storeId, nextCursor);
        }
        if (!result.has_more || afterId <= priorCursor) return;
      }
    } catch (_error) {
      // Socket reconnect will trigger another replay attempt.
    }
  };

  const start = async () => {
    try {
      const response = await fetch("/api/v1/realtime/stores", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const body = await response.json();
      const storeIds = (body.stores || []).slice(0, 500);
      if (!storeIds.length || typeof window.io !== "function") return;
      socket = window.io("/retail", { withCredentials: true });
      socket.on("connect", () => {
        for (const storeId of storeIds) {
          socket.emit("subscribe_store", { store_id: storeId }, acknowledgement => {
            if (!acknowledgement?.ok) return;
            const saved = getCursor(storeId);
            const cursor = saved || Number(acknowledgement.cursor || 0);
            stores.set(storeId, { cursor, generation: socket.io.engine?.id || socket.id || "connected" });
            void replay(storeId, stores.get(storeId).generation);
          });
        }
      });
      socket.onAny((eventName, event) => {
        if (eventName === "access.revoked") {
          showNotice("Your store or account access changed. Refresh to check your permissions.");
          socket.disconnect();
          return;
        }
        const storeId = event?.store_id;
        if (!storeId || !stores.has(storeId)) return;
        const state = stores.get(storeId);
        const eventId = Number(event.id);
        if (Number.isSafeInteger(eventId) && eventId > state.cursor) void replay(storeId, state.generation);
      });
      socket.on("disconnect", () => {
        stores.clear();
        showNotice("Realtime connection paused; reconnecting and replaying missed activity…");
      });
    } catch (_error) {
      // The page remains usable; it can be refreshed if the connection is unavailable.
    }
  };

  void start();
})();
