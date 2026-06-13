-- Chatbot drafts are now tied to qa_ticket/draft_id, not chatbot-side ticket_analysis.
-- CS automation can create ticket_analysis later, so analysis_id must be optional here.

ALTER TABLE answer_draft
    ALTER COLUMN analysis_id DROP NOT NULL;
