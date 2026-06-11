# Chatbot Tools

`db_tools.py` exposes only LangChain tool wrappers for DB reads that an agent may choose during reasoning.
Workflow-required writes call repository functions directly from the workflow nodes.

Read tools:
- `read_item_delivery_logs(account_id)`
- `read_gacha_logs(account_id)`
- `collect_user_payment_context(user_id, account_id=None)`

Repository-direct workflow writes:
- `save_qa_ticket(payload)`
- `save_answer_draft(payload)`
- `save_evidence_docs(payload)`
- `save_safety_results(payload)`
- `save_failed_query(payload)`
- `update_qa_ticket_raw_query(payload)`

The chatbot no longer writes `ticket_analysis`; CS automation owns analysis rows.
