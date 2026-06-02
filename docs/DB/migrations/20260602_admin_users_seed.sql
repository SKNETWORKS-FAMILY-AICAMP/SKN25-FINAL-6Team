-- Draft seed for the first operator account.
-- Temporary bootstrap password: ChangeMe123!
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
VALUES (
    'admin',
    '$2b$12$fzlAli6q.R3x3ZVLdxI5BO6cnUmQiNs4KOLEVKkt23nOVU//LH5hm',
    'Primary Admin',
    'admin',
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
