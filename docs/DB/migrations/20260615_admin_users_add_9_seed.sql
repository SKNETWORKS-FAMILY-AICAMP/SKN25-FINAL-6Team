-- Additional operator/reviewer seed accounts.
-- Temporary bootstrap password for all rows: ChangeMe123!
-- Rotate immediately after first login.

INSERT INTO admin_users (
    login_id,
    password_hash,
    display_name,
    role,
    status,
    password_updated_at,
    created_at
)
VALUES
    (
        'operator01',
        '$2b$12$EMX3pYSNr4qAsHsbzPkIV.bnwexQ67AFkjJD/ZeN6/lOeZ4HcQZdG',
        'Operator 01',
        'admin',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'operator02',
        '$2b$12$n7uKfthdF6uc0E6zjdGOwuxpGH4VgyUJWYdS/2LHse6LujmM9be3u',
        'Operator 02',
        'admin',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'operator03',
        '$2b$12$1zY3huLpMzYzj59m5pTKueSxltn.GFeDxtK9ei/6MULUfZp37tYKS',
        'Operator 03',
        'admin',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'operator04',
        '$2b$12$0v7ddJL780S9M5d51Ge79ewp2qJT7.fF/cf69ofaumpXYETIKKKDO',
        'Operator 04',
        'admin',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'operator05',
        '$2b$12$dAB6fuP9yYRD4AKH80VOSuUAEzxtgd0TWqqAiZkO59FL9vMq4RdSO',
        'Operator 05',
        'admin',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'reviewer01',
        '$2b$12$AmzdgxyJBd2ITemUldf.UeirP3oxkLTLWDPJIjwv4Da6VBh15f36W',
        'Reviewer 01',
        'reviewer',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'reviewer02',
        '$2b$12$fJj1YGh6vEqJtPoG2fFwFu3Wp4gjgRKfx6qilV4LBpRW7uKmyMEaK',
        'Reviewer 02',
        'reviewer',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'reviewer03',
        '$2b$12$dRWpk4Dvp5B0Oa3sjb4gMO1RSjWqPYGc5jNlZsCrsRyTEwn.R.ti.',
        'Reviewer 03',
        'reviewer',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'reviewer04',
        '$2b$12$vlo8HNy.a3QRI0ZwHR0Xa..YqN.X8GTDF6asZWBWBGktZPyIdiSW6',
        'Reviewer 04',
        'reviewer',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    )
ON CONFLICT (login_id) DO UPDATE
SET
    password_hash = EXCLUDED.password_hash,
    display_name = EXCLUDED.display_name,
    role = EXCLUDED.role,
    status = EXCLUDED.status,
    password_updated_at = CURRENT_TIMESTAMP;
