-- admin_event_logs is no longer used by the chatbot runtime.
-- Runtime observability remains available through console JSON logs and LangSmith metadata.

DROP TABLE IF EXISTS admin_event_logs;
