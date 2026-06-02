async function apiFetch(path, options = {}) {
  const response = await fetch(`/chatbot/api${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || JSON.stringify(payload);
    } catch (_error) {
      detail = await response.text();
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return response.json();
}

window.ChatbotApi = {
  getServerRegions() {
    return apiFetch("/server-regions");
  },

  getTickets(params) {
    const query = params instanceof URLSearchParams ? params.toString() : String(params || "");
    return apiFetch(`/tickets?${query}`);
  },

  login(payload) {
    return apiFetch("/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  sendChat(payload) {
    return apiFetch("/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
