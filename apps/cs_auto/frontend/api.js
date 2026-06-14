(function attachCsAutoApi(global) {
  const API_BASE_URL = global.CS_AUTO_API_BASE_URL || "/cs-auto/api";

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      },
      ...options
    });

    if (!response.ok) {
      let errorPayload = null;
      try {
        errorPayload = await response.json();
      } catch {
        try {
          const text = await response.text();
          errorPayload = text ? { message: text } : null;
        } catch {
          errorPayload = null;
        }
      }

      return {
        ok: false,
        status: response.status,
        ...(errorPayload && typeof errorPayload === "object" ? errorPayload : {}),
        message:
          errorPayload && typeof errorPayload === "object" && errorPayload.message
            ? errorPayload.message
            : errorPayload && typeof errorPayload === "object" && errorPayload.detail
              ? String(errorPayload.detail)
              : `HTTP ${response.status}`
      };
    }

    return response.json();
  }

  global.CSAutoApi = {
    request,
    getTickets(limit = 50) {
      return request(`/tickets?limit=${limit}`);
    },
    getTicketDetail(ticketId) {
      return request(`/tickets/${ticketId}`);
    },
    login(loginId, password) {
      return request("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          login_id: loginId,
          password
        })
      });
    },
    logout(adminId, sessionId) {
      return request("/auth/logout", {
        method: "POST",
        body: JSON.stringify({
          admin_id: adminId,
          session_id: sessionId
        })
      });
    },
    updateDraft(ticketId, draftId, editedText, adminId) {
      return request(`/tickets/${ticketId}/draft`, {
        method: "PATCH",
        body: JSON.stringify({
          draft_id: draftId,
          edited_text: editedText,
          admin_id: adminId,
          edit_reason: "프론트엔드 수정 완료"
        })
      });
    },
    approveDraft(ticketId, draftId, finalText, adminId) {
      return request(`/tickets/${ticketId}/draft/approve`, {
        method: "POST",
        body: JSON.stringify({
          draft_id: draftId,
          final_text: finalText,
          admin_id: adminId,
          edit_reason: "프론트엔드 답변 완료"
        })
      });
    },
    sendAnswerEmail(ticketId, adminId) {
      return request(`/tickets/${ticketId}/send-email`, {
        method: "POST",
        body: JSON.stringify({
          admin_id: adminId
        })
      });
    },
    regenerateDraft(ticketId, draftId, reason, adminId) {
      return request(`/tickets/${ticketId}/draft/regenerate`, {
        method: "POST",
        body: JSON.stringify({
          draft_id: draftId,
          regeneration_reason: reason,
          admin_id: adminId
        })
      });
    }
  };
})(window);
