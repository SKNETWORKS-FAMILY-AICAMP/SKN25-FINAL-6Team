-- Draft migration for operator/admin authentication.
-- Keep this file in sync with docs/DB/migrations/20260602_admin_users_auth.sql.

CREATE SEQUENCE IF NOT EXISTS admin_users_admin_id_seq;

CREATE TABLE IF NOT EXISTS admin_users (
    admin_id integer PRIMARY KEY DEFAULT nextval('admin_users_admin_id_seq'),
    login_id varchar(100) NOT NULL,
    password_hash text NOT NULL,
    display_name varchar(100) NOT NULL,
    role varchar(30) NOT NULL,
    status varchar(30) NOT NULL DEFAULT 'active',
    last_login_at timestamp,
    password_updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_admin_users_login_id UNIQUE (login_id),
    CONSTRAINT ck_admin_users_role CHECK (role IN ('admin', 'reviewer')),
    CONSTRAINT ck_admin_users_status CHECK (status IN ('active', 'inactive', 'locked'))
);

ALTER SEQUENCE admin_users_admin_id_seq OWNED BY admin_users.admin_id;

ALTER TABLE qa_ticket
    ADD COLUMN IF NOT EXISTS assignee_admin_id integer;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_qa_ticket_assignee_admin_id'
    ) THEN
        ALTER TABLE qa_ticket
            ADD CONSTRAINT fk_qa_ticket_assignee_admin_id
            FOREIGN KEY (assignee_admin_id)
            REFERENCES admin_users (admin_id)
            ON UPDATE NO ACTION
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_qa_ticket_assignee_admin_id
    ON qa_ticket (assignee_admin_id);

ALTER TABLE admin_event_logs
    ADD COLUMN IF NOT EXISTS actor_admin_id integer;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_admin_event_logs_actor_admin_id'
    ) THEN
        ALTER TABLE admin_event_logs
            ADD CONSTRAINT fk_admin_event_logs_actor_admin_id
            FOREIGN KEY (actor_admin_id)
            REFERENCES admin_users (admin_id)
            ON UPDATE NO ACTION
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_admin_event_logs_actor_admin_id
    ON admin_event_logs (actor_admin_id);

COMMENT ON TABLE admin_users IS 'Dedicated operator/admin login accounts';
COMMENT ON COLUMN qa_ticket.assignee_admin_id IS 'Assigned operator reference to admin_users.admin_id';
COMMENT ON COLUMN admin_event_logs.actor_admin_id IS 'Operator/admin actor reference to admin_users.admin_id';
