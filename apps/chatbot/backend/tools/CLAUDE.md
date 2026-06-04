# Chatbot Tools

`db_tools.py` exposes LangChain tool wrappers around repository functions.

Read tools:
- `verify_user_login(email, password)`
- `read_payments(account_id)`
- `read_refunds(payment_id)`
- `read_item_delivery_logs(account_id)`
- `read_gacha_logs(account_id)`
- `collect_user_payment_context(user_id, account_id=None)`

Write tools:
- `write_qa_ticket(payload)`
- `write_answer_draft(payload)`
- `write_evidence_docs(payload)`
- `write_safety_results(payload)`
- `write_final_response(payload)`
- `write_failed_query(payload)`
- `write_voc_feedback(payload)`
- `update_qa_ticket_status(payload)`

The chatbot no longer writes `ticket_analysis`; CS automation owns analysis rows.
