-- Chatbot session_id now uses turn IDs such as "123456789-1", "123456789-2".
-- Store session_id as text so each ticket can keep its own turn while sharing the same session prefix.

ALTER TABLE qa_ticket
    ALTER COLUMN session_id TYPE TEXT
    USING session_id::TEXT;
