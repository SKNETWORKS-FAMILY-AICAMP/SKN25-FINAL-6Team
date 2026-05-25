"""Streamlit entry page for the chatbot UI."""

from __future__ import annotations

import os

import requests
import streamlit as st


DEFAULT_API_BASE_URL = os.environ.get("CHATBOT_API_BASE_URL") or "http://127.0.0.1:8000"


st.set_page_config(page_title="Chatbot", layout="wide")

st.title("Chatbot")
st.caption("챗봇 서비스 화면입니다. API 연결 상태를 확인합니다.")

api_base_url = st.sidebar.text_input("API URL", value=DEFAULT_API_BASE_URL).rstrip("/")

try:
    response = requests.get(f"{api_base_url}/health", timeout=10)
    response.raise_for_status()
except requests.RequestException as exc:
    st.error(f"챗봇 API 상태를 확인하지 못했습니다: {exc}")
else:
    st.success("챗봇 API가 정상 응답했습니다.")
