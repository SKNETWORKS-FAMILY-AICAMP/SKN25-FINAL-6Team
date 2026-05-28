"""Ticket summary rendering helpers for operation Streamlit pages."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_ticket_card(ticket: dict[str, Any]) -> None:
    title = ticket.get("title") or "(제목 없음)"
    status = ticket.get("status") or "-"
    nickname = ticket.get("nickname") or "-"
    ticket_id = ticket.get("ticket_id")
    risk_level = ticket.get("risk_level") or "-"
    routing_target = ticket.get("routing_target") or "-"

    with st.container(border=True):
        st.markdown(f"**#{ticket_id} {title}**")
        cols = st.columns(4)
        cols[0].metric("상태", status)
        cols[1].metric("사용자", nickname)
        cols[2].metric("위험도", risk_level)
        cols[3].metric("라우팅", routing_target)
