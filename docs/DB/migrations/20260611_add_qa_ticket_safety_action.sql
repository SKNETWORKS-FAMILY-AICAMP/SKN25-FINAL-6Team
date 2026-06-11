-- qa_ticket에 챗봇 safety 처리 결과를 저장하는 컬럼 추가.
-- raw_query는 기존 컬럼을 그대로 사용하므로 raw_content 컬럼은 추가하지 않는다.

ALTER TABLE qa_ticket ADD COLUMN IF NOT EXISTS safety_action VARCHAR(50);
