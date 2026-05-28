-- Reference migration for a DB-managed ID strategy.
-- The live database currently uses application-assigned IDs for these tables.
-- Apply only if you want PostgreSQL to allocate primary keys for workflow writes.

CREATE SEQUENCE IF NOT EXISTS ticket_analysis_analysis_id_seq OWNED BY ticket_analysis.analysis_id;
SELECT setval(
    'ticket_analysis_analysis_id_seq',
    COALESCE((SELECT MAX(analysis_id) FROM ticket_analysis), 0) + 1,
    false
);
ALTER TABLE ticket_analysis
    ALTER COLUMN analysis_id SET DEFAULT nextval('ticket_analysis_analysis_id_seq');

CREATE SEQUENCE IF NOT EXISTS answer_draft_draft_id_seq OWNED BY answer_draft.draft_id;
SELECT setval(
    'answer_draft_draft_id_seq',
    COALESCE((SELECT MAX(draft_id) FROM answer_draft), 0) + 1,
    false
);
ALTER TABLE answer_draft
    ALTER COLUMN draft_id SET DEFAULT nextval('answer_draft_draft_id_seq');

CREATE SEQUENCE IF NOT EXISTS evidence_docs_evidence_id_seq OWNED BY evidence_docs.evidence_id;
SELECT setval(
    'evidence_docs_evidence_id_seq',
    COALESCE((SELECT MAX(evidence_id) FROM evidence_docs), 0) + 1,
    false
);
ALTER TABLE evidence_docs
    ALTER COLUMN evidence_id SET DEFAULT nextval('evidence_docs_evidence_id_seq');

CREATE SEQUENCE IF NOT EXISTS safety_results_safety_id_seq OWNED BY safety_results.safety_id;
SELECT setval(
    'safety_results_safety_id_seq',
    COALESCE((SELECT MAX(safety_id) FROM safety_results), 0) + 1,
    false
);
ALTER TABLE safety_results
    ALTER COLUMN safety_id SET DEFAULT nextval('safety_results_safety_id_seq');
