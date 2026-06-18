-- Live DB candidate extraction queries for routing-target gold expansion.
--
-- Purpose
-- - Expand the current live-sampled gold set to 20-50 reviewed candidates.
-- - Return rows already shaped close to the JSON dataset fields:
--   ticket, routing_target, gold_facts, gold_policy, must_include, must_not_include.
--
-- Usage
-- 1. Run one query block at a time.
-- 2. Review the returned candidates manually before freezing them into the gold JSON.
-- 3. Adjust the per-query LIMIT values to reach the target sample size.
--
-- Notes
-- - These queries infer routing candidates directly from qa_ticket because ticket_analysis
--   may not yet be populated.
-- - The live document store assumed here is:
--   documents / documents_chunks / documents_embeddings
-- - JSON payloads are intentionally compact enough to serialize directly into the dataset.


-- =========================================================
-- 0. Shared ticket intent classifier
-- =========================================================
-- Reuse this CTE at the top of each query block if you want to tune the heuristics.

WITH classified_tickets AS (
    SELECT
        q.ticket_id,
        q.account_id,
        q.user_id,
        q.title,
        q.raw_query,
        q.status,
        q.inquiry_created_at,
        CASE
            WHEN
                q.raw_query ILIKE '%비밀번호%'
                OR q.title ILIKE '%비밀번호%'
            THEN 'account_password'
            WHEN
                q.raw_query ILIKE '%계정 삭제%'
                OR q.title ILIKE '%계정 삭제%'
            THEN 'account_delete'
            WHEN
                q.raw_query ILIKE '%최근에 나온 공지%'
                OR q.raw_query ILIKE '%최근에 업데이트된 공지%'
                OR q.raw_query ILIKE '%최신 공지%'
                OR q.title ILIKE '%공지%'
            THEN 'latest_notice'
            WHEN
                q.raw_query ILIKE '%우편%'
                OR q.raw_query ILIKE '%우편함%'
                OR q.raw_query ILIKE '%보상%'
            THEN 'mail_reward'
            WHEN
                q.raw_query ILIKE '%결제가 안%'
                OR q.raw_query ILIKE '%결제 안%'
                OR q.raw_query ILIKE '%결제 실패%'
            THEN 'payment_failed'
            WHEN
                q.raw_query ILIKE '%환불%'
                OR q.title ILIKE '%환불%'
            THEN 'refund'
            WHEN
                q.raw_query ILIKE '%중복결제%'
                OR q.raw_query ILIKE '%중복 결제%'
            THEN 'duplicate_payment'
            WHEN
                q.raw_query ILIKE '%로드되지%'
                OR q.raw_query ILIKE '%지급되지%'
                OR q.raw_query ILIKE '%미지급%'
                OR q.raw_query ILIKE '%상품이 로드%'
            THEN 'payment_delivery_issue'
            WHEN
                q.raw_query ILIKE '%가챠%'
                OR q.raw_query ILIKE '%뽑기%'
                OR q.raw_query ILIKE '%픽뚫%'
                OR q.raw_query ILIKE '%기원%'
            THEN 'gacha'
            ELSE NULL
        END AS intent_family
    FROM qa_ticket q
)
SELECT *
FROM classified_tickets
WHERE intent_family IS NOT NULL
ORDER BY inquiry_created_at DESC NULLS LAST
LIMIT 20;


-- =========================================================
-- 1. DOC_ONLY candidate extractor
-- =========================================================
-- Best for:
-- - password/account procedure
-- - latest notice lookup
-- - other FAQ/procedure tickets where account state is irrelevant
--
-- Result columns:
-- - ticket_json
-- - gold_policy_json

WITH classified_tickets AS (
    SELECT
        q.ticket_id,
        q.account_id,
        q.user_id,
        q.title,
        q.raw_query,
        q.status,
        q.inquiry_created_at,
        CASE
            WHEN q.raw_query ILIKE '%비밀번호%' OR q.title ILIKE '%비밀번호%' THEN 'account_password'
            WHEN q.raw_query ILIKE '%계정 삭제%' OR q.title ILIKE '%계정 삭제%' THEN 'account_delete'
            WHEN q.raw_query ILIKE '%최근에 나온 공지%' OR q.raw_query ILIKE '%최근에 업데이트된 공지%' OR q.raw_query ILIKE '%최신 공지%' THEN 'latest_notice'
            WHEN q.raw_query ILIKE '%우편%' OR q.raw_query ILIKE '%우편함%' OR q.raw_query ILIKE '%보상%' THEN 'mail_reward'
            ELSE NULL
        END AS intent_family
    FROM qa_ticket q
),
doc_family_map AS (
    SELECT
        d.documents_id,
        d.source_type,
        d.category,
        d.title,
        c.chunk_id,
        c.chunk_order,
        c.chunk_text,
        CASE
            WHEN d.documents_id = 'QNA-GSN-3' THEN 'account_password'
            WHEN d.documents_id = 'NVC-NOT-1' THEN 'latest_notice'
            WHEN d.documents_id = 'NVC-NOT-2' THEN 'mail_reward'
            WHEN d.documents_id = 'NVC-NOT-3' THEN 'mail_reward'
            ELSE NULL
        END AS intent_family
    FROM documents d
    JOIN documents_chunks c ON c.document_id = d.documents_id
),
ranked_doc_candidates AS (
    SELECT
        t.ticket_id,
        t.account_id,
        t.user_id,
        t.raw_query,
        t.inquiry_created_at,
        t.intent_family,
        m.documents_id,
        m.source_type,
        m.category,
        m.title,
        m.chunk_id,
        m.chunk_order,
        m.chunk_text,
        ROW_NUMBER() OVER (
            PARTITION BY t.ticket_id
            ORDER BY m.documents_id, m.chunk_order
        ) AS doc_rank
    FROM classified_tickets t
    JOIN doc_family_map m ON m.intent_family = t.intent_family
    WHERE t.intent_family IS NOT NULL
)
SELECT
    ticket_id,
    'doc_only' AS routing_target,
    jsonb_build_object(
        'account_id', account_id,
        'user_id', user_id,
        'created_at', inquiry_created_at,
        'question', raw_query
    ) AS ticket_json,
    jsonb_build_object(
        'documents',
        jsonb_agg(
            jsonb_build_object(
                'document_id', documents_id,
                'chunk_id', chunk_id,
                'source_type', source_type,
                'category', category,
                'title', title
            )
            ORDER BY doc_rank
        )
    ) AS gold_policy_json
FROM ranked_doc_candidates
WHERE doc_rank <= 2
GROUP BY ticket_id, account_id, user_id, inquiry_created_at, raw_query
ORDER BY ticket_id DESC
LIMIT 20;


-- =========================================================
-- 2. DB_ONLY candidate extractor
-- =========================================================
-- Best for:
-- - payment status checks
-- - refund/account-state issues grounded in structured logs only
-- - gacha-history disputes that must not rely on FAQ prose
--
-- Result columns:
-- - ticket_json
-- - gold_facts_json

WITH classified_tickets AS (
    SELECT
        q.ticket_id,
        q.account_id,
        q.user_id,
        q.raw_query,
        q.inquiry_created_at,
        CASE
            WHEN q.raw_query ILIKE '%결제가 안%' OR q.raw_query ILIKE '%결제 안%' OR q.raw_query ILIKE '%결제 실패%' THEN 'payment_failed'
            WHEN q.raw_query ILIKE '%환불%' THEN 'refund'
            WHEN q.raw_query ILIKE '%가챠%' OR q.raw_query ILIKE '%뽑기%' OR q.raw_query ILIKE '%픽뚫%' OR q.raw_query ILIKE '%기원%' THEN 'gacha'
            ELSE NULL
        END AS intent_family
    FROM qa_ticket q
),
latest_account AS (
    SELECT
        a.account_id,
        jsonb_build_object(
            'account_status', a.account_status,
            'server_region', a.server_region,
            'uid', a.uid
        ) AS account_json
    FROM game_accounts a
),
latest_payment AS (
    SELECT DISTINCT ON (p.account_id)
        p.account_id,
        jsonb_build_object(
            'payment_id', p.payment_id,
            'product_name', p.product_name,
            'product_type', p.product_type,
            'amount', p.amount,
            'currency', p.currency,
            'payment_method', p.payment_method,
            'payment_status', p.payment_status,
            'paid_at', p.paid_at
        ) AS payment_json
    FROM payments p
    ORDER BY p.account_id, p.paid_at DESC NULLS LAST, p.payment_id DESC
),
latest_refund AS (
    SELECT DISTINCT ON (p.account_id)
        p.account_id,
        jsonb_build_object(
            'refund_id', r.refund_id,
            'payment_id', r.payment_id,
            'refund_status', r.refund_status,
            'refund_reason', r.refund_reason,
            'requested_at', r.requested_at,
            'processed_at', r.processed_at
        ) AS refund_json
    FROM payments p
    JOIN refunds r ON r.payment_id = p.payment_id
    ORDER BY p.account_id, r.requested_at DESC NULLS LAST, r.refund_id DESC
),
latest_delivery AS (
    SELECT DISTINCT ON (d.account_id)
        d.account_id,
        jsonb_build_object(
            'delivery_id', d.delivery_id,
            'payment_id', d.payment_id,
            'item_name', d.item_name,
            'quantity', d.quantity,
            'delivery_status', d.delivery_status,
            'expected_at', d.expected_at,
            'delivered_at', d.delivered_at
        ) AS delivery_json
    FROM item_delivery_logs d
    ORDER BY d.account_id, d.expected_at DESC NULLS LAST, d.delivery_id DESC
),
latest_gacha_5star AS (
    SELECT
        g.account_id,
        jsonb_agg(
            jsonb_build_object(
                'gacha_id', g.gacha_id,
                'banner_name', g.banner_name,
                'item_name', g.item_name,
                'item_type', g.item_type,
                'rarity', g.rarity,
                'pity_count', g.pity_count,
                'pulled_at', g.pulled_at
            )
            ORDER BY g.pulled_at DESC NULLS LAST, g.gacha_id DESC
        ) FILTER (WHERE g.rarity = '5성') AS gacha_5star_json
    FROM (
        SELECT
            g.*,
            ROW_NUMBER() OVER (
                PARTITION BY g.account_id, g.rarity
                ORDER BY g.pulled_at DESC NULLS LAST, g.gacha_id DESC
            ) AS rarity_rank
        FROM gacha_logs g
    ) g
    WHERE g.rarity_rank <= 3
    GROUP BY g.account_id
)
SELECT
    t.ticket_id,
    'DB_only' AS routing_target,
    jsonb_build_object(
        'account_id', t.account_id,
        'user_id', t.user_id,
        'created_at', t.inquiry_created_at,
        'question', t.raw_query
    ) AS ticket_json,
    jsonb_build_object(
        'account', la.account_json,
        'latest_payment', lp.payment_json,
        'latest_refund', lr.refund_json,
        'latest_delivery', ld.delivery_json,
        'recent_5star_gacha', lg.gacha_5star_json
    ) AS gold_facts_json
FROM classified_tickets t
JOIN latest_account la ON la.account_id = t.account_id
LEFT JOIN latest_payment lp ON lp.account_id = t.account_id
LEFT JOIN latest_refund lr ON lr.account_id = t.account_id
LEFT JOIN latest_delivery ld ON ld.account_id = t.account_id
LEFT JOIN latest_gacha_5star lg ON lg.account_id = t.account_id
WHERE t.intent_family IN ('payment_failed', 'refund', 'gacha')
ORDER BY t.inquiry_created_at DESC NULLS LAST
LIMIT 20;


-- =========================================================
-- 3. DB&DOC candidate extractor
-- =========================================================
-- Best for:
-- - payment delivered/not-delivered issues with FAQ instructions
-- - duplicate-payment or battle-pass questions needing both logs and FAQ
--
-- Result columns:
-- - ticket_json
-- - gold_facts_json
-- - gold_policy_json

WITH classified_tickets AS (
    SELECT
        q.ticket_id,
        q.account_id,
        q.user_id,
        q.raw_query,
        q.inquiry_created_at,
        CASE
            WHEN q.raw_query ILIKE '%로드되지%' OR q.raw_query ILIKE '%지급되지%' OR q.raw_query ILIKE '%미지급%' OR q.raw_query ILIKE '%상품이 로드%' THEN 'payment_delivery_issue'
            WHEN q.raw_query ILIKE '%중복결제%' OR q.raw_query ILIKE '%중복 결제%' THEN 'duplicate_payment'
            WHEN q.raw_query ILIKE '%환불%' AND (q.raw_query ILIKE '%기행%' OR q.raw_query ILIKE '%공월%' OR q.raw_query ILIKE '%결제%') THEN 'refund_after_purchase'
            ELSE NULL
        END AS intent_family
    FROM qa_ticket q
),
policy_docs AS (
    SELECT
        d.documents_id,
        d.source_type,
        d.category,
        d.title,
        c.chunk_id,
        c.chunk_order,
        CASE
            WHEN d.documents_id = 'QNA-GSN-5' THEN 'payment_delivery_issue'
            WHEN d.documents_id = 'QNA-GSN-9' THEN 'duplicate_payment'
            WHEN d.documents_id IN ('QNA-GSN-7', 'QNA-GSN-8') THEN 'refund_after_purchase'
            ELSE NULL
        END AS intent_family
    FROM documents d
    JOIN documents_chunks c ON c.document_id = d.documents_id
),
latest_account AS (
    SELECT
        a.account_id,
        jsonb_build_object(
            'account_status', a.account_status,
            'server_region', a.server_region,
            'uid', a.uid
        ) AS account_json
    FROM game_accounts a
),
payments_ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY p.account_id
            ORDER BY p.paid_at DESC NULLS LAST, p.payment_id DESC
        ) AS payment_rank
    FROM payments p
),
deliveries_ranked AS (
    SELECT
        d.*,
        ROW_NUMBER() OVER (
            PARTITION BY d.account_id
            ORDER BY d.expected_at DESC NULLS LAST, d.delivery_id DESC
        ) AS delivery_rank
    FROM item_delivery_logs d
),
refunds_ranked AS (
    SELECT
        p.account_id,
        r.refund_id,
        r.payment_id,
        r.refund_status,
        r.refund_reason,
        r.requested_at,
        r.processed_at,
        ROW_NUMBER() OVER (
            PARTITION BY p.account_id
            ORDER BY r.requested_at DESC NULLS LAST, r.refund_id DESC
        ) AS refund_rank
    FROM payments p
    JOIN refunds r ON r.payment_id = p.payment_id
)
SELECT
    t.ticket_id,
    'DB&DOC' AS routing_target,
    jsonb_build_object(
        'account_id', t.account_id,
        'user_id', t.user_id,
        'created_at', t.inquiry_created_at,
        'question', t.raw_query
    ) AS ticket_json,
    jsonb_build_object(
        'account', la.account_json,
        'payments',
        jsonb_agg(
            DISTINCT jsonb_build_object(
                'payment_id', p.payment_id,
                'product_name', p.product_name,
                'product_type', p.product_type,
                'amount', p.amount,
                'currency', p.currency,
                'payment_method', p.payment_method,
                'payment_status', p.payment_status,
                'paid_at', p.paid_at
            )
        ) FILTER (WHERE p.payment_rank <= 2),
        'deliveries',
        jsonb_agg(
            DISTINCT jsonb_build_object(
                'delivery_id', d.delivery_id,
                'payment_id', d.payment_id,
                'item_name', d.item_name,
                'quantity', d.quantity,
                'delivery_status', d.delivery_status,
                'expected_at', d.expected_at,
                'delivered_at', d.delivered_at
            )
        ) FILTER (WHERE d.delivery_rank <= 4),
        'refunds',
        jsonb_agg(
            DISTINCT jsonb_build_object(
                'refund_id', r.refund_id,
                'payment_id', r.payment_id,
                'refund_status', r.refund_status,
                'refund_reason', r.refund_reason,
                'requested_at', r.requested_at,
                'processed_at', r.processed_at
            )
        ) FILTER (WHERE r.refund_rank <= 2)
    ) AS gold_facts_json,
    jsonb_build_object(
        'documents',
        jsonb_agg(
            DISTINCT jsonb_build_object(
                'document_id', doc.documents_id,
                'chunk_id', doc.chunk_id,
                'source_type', doc.source_type,
                'category', doc.category,
                'title', doc.title
            )
        )
    ) AS gold_policy_json
FROM classified_tickets t
JOIN latest_account la ON la.account_id = t.account_id
LEFT JOIN payments_ranked p ON p.account_id = t.account_id
LEFT JOIN deliveries_ranked d ON d.account_id = t.account_id
LEFT JOIN refunds_ranked r ON r.account_id = t.account_id
JOIN policy_docs doc ON doc.intent_family = t.intent_family
WHERE t.intent_family IS NOT NULL
GROUP BY
    t.ticket_id,
    t.account_id,
    t.user_id,
    t.inquiry_created_at,
    t.raw_query,
    la.account_json
ORDER BY t.inquiry_created_at DESC NULLS LAST
LIMIT 20;


-- =========================================================
-- 4. Balanced review queue
-- =========================================================
-- Union 3 candidate groups into one queue for manual review.
-- Increase each block LIMIT to roughly 10-20 to build a 30-50 row review batch.

WITH doc_only_candidates AS (
    SELECT ticket_id, 'doc_only' AS routing_target
    FROM (
        WITH classified_tickets AS (
            SELECT
                q.ticket_id,
                q.inquiry_created_at,
                CASE
                    WHEN q.raw_query ILIKE '%비밀번호%' OR q.title ILIKE '%비밀번호%' THEN 'account_password'
                    WHEN q.raw_query ILIKE '%최근에 나온 공지%' OR q.raw_query ILIKE '%최신 공지%' THEN 'latest_notice'
                    ELSE NULL
                END AS intent_family
            FROM qa_ticket q
        )
        SELECT ticket_id
        FROM classified_tickets
        WHERE intent_family IS NOT NULL
        ORDER BY inquiry_created_at DESC NULLS LAST
        LIMIT 10
    ) s
),
db_only_candidates AS (
    SELECT ticket_id, 'DB_only' AS routing_target
    FROM (
        WITH classified_tickets AS (
            SELECT
                q.ticket_id,
                q.inquiry_created_at,
                CASE
                    WHEN q.raw_query ILIKE '%결제가 안%' OR q.raw_query ILIKE '%결제 안%' THEN 'payment_failed'
                    WHEN q.raw_query ILIKE '%환불%' THEN 'refund'
                    WHEN q.raw_query ILIKE '%뽑기%' OR q.raw_query ILIKE '%가챠%' OR q.raw_query ILIKE '%픽뚫%' THEN 'gacha'
                    ELSE NULL
                END AS intent_family
            FROM qa_ticket q
        )
        SELECT ticket_id
        FROM classified_tickets
        WHERE intent_family IS NOT NULL
        ORDER BY inquiry_created_at DESC NULLS LAST
        LIMIT 10
    ) s
),
hybrid_candidates AS (
    SELECT ticket_id, 'DB&DOC' AS routing_target
    FROM (
        WITH classified_tickets AS (
            SELECT
                q.ticket_id,
                q.inquiry_created_at,
                CASE
                    WHEN q.raw_query ILIKE '%로드되지%' OR q.raw_query ILIKE '%지급되지%' OR q.raw_query ILIKE '%미지급%' THEN 'payment_delivery_issue'
                    WHEN q.raw_query ILIKE '%중복결제%' OR q.raw_query ILIKE '%중복 결제%' THEN 'duplicate_payment'
                    ELSE NULL
                END AS intent_family
            FROM qa_ticket q
        )
        SELECT ticket_id
        FROM classified_tickets
        WHERE intent_family IS NOT NULL
        ORDER BY inquiry_created_at DESC NULLS LAST
        LIMIT 10
    ) s
)
SELECT *
FROM doc_only_candidates
UNION ALL
SELECT *
FROM db_only_candidates
UNION ALL
SELECT *
FROM hybrid_candidates
ORDER BY routing_target, ticket_id DESC;
