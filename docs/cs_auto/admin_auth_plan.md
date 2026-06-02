# Admin Auth Plan

## Goal

- Replace hardcoded operator login with DB-backed authentication.
- Store operator identity separately from `community_users`.
- Move ticket assignment and review history from string IDs toward `admin_users.admin_id`.

## Schema Draft

### New table: `admin_users`

| Column | Type | Notes |
| --- | --- | --- |
| `admin_id` | `integer` | PK, sequence-backed |
| `login_id` | `varchar(100)` | unique login identifier shown nowhere except login |
| `password_hash` | `text` | bcrypt hash |
| `display_name` | `varchar(100)` | UI display name |
| `role` | `varchar(30)` | `admin` or `reviewer` |
| `status` | `varchar(30)` | `active`, `inactive`, `locked` |
| `last_login_at` | `timestamp` | updated only on successful login |
| `password_updated_at` | `timestamp` | password rotation audit |
| `created_at` | `timestamp` | row creation time |

### Transition columns

- `qa_ticket.assignee_admin_id integer null`
- `admin_event_logs.actor_admin_id integer null`

Rationale:

- `qa_ticket.assignee_id` already carries string demo IDs in current code, so immediate replacement is risky.
- A transition phase lets the application dual-read while new writes move to `admin_id`.
- `admin_event_logs.metadata.reviewer_id` can remain for a short compatibility window, but new writes should also set `actor_admin_id`.

## API Draft

### POST `/auth/admin/login`

Request:

```json
{
  "login_id": "admin",
  "password": "ChangeMe123!"
}
```

Response:

```json
{
  "login_success": true,
  "admin_id": 1,
  "login_id": "admin",
  "display_name": "Primary Admin",
  "role": "admin",
  "status": "active",
  "message": "Login succeeded."
}
```

Failure response:

```json
{
  "login_success": false,
  "admin_id": null,
  "login_id": "admin",
  "display_name": null,
  "role": null,
  "status": null,
  "message": "Login ID or password is invalid."
}
```

Validation rules:

- Read by `login_id`.
- Verify password with bcrypt.
- Reject when `status != 'active'`.
- Update `last_login_at = CURRENT_TIMESTAMP` only on success.

### Ticket and review write API changes

- `POST /tickets/{ticket_id}/assign`
  - Request should move from `reviewer_id: str` to `admin_id: int`
  - Optional compatibility field: `login_id: str`
- `PATCH /drafts/{draft_id}`
  - Request should move from `reviewer_id: str | null` to `admin_id: int | null`
- `POST /drafts/{draft_id}/approve`
  - Same change: `admin_id`
- `POST /drafts/{draft_id}/reject`
  - Same change: `admin_id`

Recommended response shape for current operator:

```json
{
  "admin_id": 3,
  "login_id": "reviewer_01",
  "display_name": "Reviewer 01",
  "role": "reviewer"
}
```

## Backend Change Plan

### 1. Shared auth repository/service

Add a dedicated repository/service pair parallel to the existing community-user login flow:

- `apps/cs_auto/backend/repository/admin_account_repository.py`
- `apps/cs_auto/backend/service/admin_account_service.py`

Responsibilities:

- `read_admin_by_login_id(login_id)`
- `verify_admin_login(login_id, password)`
- `touch_admin_last_login(admin_id)`

Use the same bcrypt helper pattern already used in:

- [apps/cs_auto/backend/repository/account_repository.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/repository/account_repository.py:12)
- [apps/cs_auto/backend/utils/passwords.py](/C:/SKN25-FINAL-6Team/apps/cs_auto/backend/utils/passwords.py:6)

### 2. API model changes

In `apps/cs_auto/backend/api/main.py`:

- Add `AdminLoginRequest`
- Add `AdminLoginResponse`
- Add `POST /auth/admin/login`
- Change assignment/review request models from `reviewer_id: str` to `admin_id: int`
- While migrating, allow both fields and normalize to `admin_id`

### 3. Ticket query changes

Update list/detail queries to join `admin_users` for display:

- Select `t.assignee_admin_id`
- Left join `admin_users au ON au.admin_id = t.assignee_admin_id`
- Return `assignee_login_id`, `assignee_display_name`, `assignee_role`

### 4. Review log write changes

When writing `admin_event_logs`:

- Set `actor_admin_id`
- Keep `metadata.reviewer_id` temporarily as `login_id` for backward compatibility
- Add `metadata.display_name` only if the UI still needs immediate rendering without join logic

## Frontend Change Plan

### `apps/cs_auto/frontend/static/api.js`

Replace:

- `DEMO_ACCOUNTS`
- local password comparison in `doLogin()`

With:

- `POST /auth/admin/login`
- Store current operator as:

```js
appState.currentReviewer = {
  adminId: 3,
  loginId: "reviewer_01",
  displayName: "Reviewer 01",
  role: "reviewer"
};
```

Required follow-up changes:

- assignment filter should use `currentReviewer.adminId`
- display areas should render `displayName` and `role`
- review action payloads should send `admin_id`

### `apps/dashboard/frontend/static/index.html`

Current dashboard login is also hardcoded demo auth.

Recommended options:

1. Short term: mirror the same `/auth/admin/login` API in dashboard backend.
2. Better: move dashboard login JS out of static HTML into a shared API helper and use the same auth contract as `cs_auto`.

## Rollout Plan

1. Apply `admin_users` migration and bootstrap seed.
2. Deploy backend support for `/auth/admin/login`.
3. Change new assignment/review writes to use `admin_id`.
4. Change UI to use server login response instead of `DEMO_ACCOUNTS`.
5. Dual-read old and new reviewer fields during migration.
6. After old demo data is no longer needed:
   - stop writing `metadata.reviewer_id`
   - stop reading `qa_ticket.assignee_id`
   - optionally drop legacy string fields if they exist only for demo flow

## Open Decisions

- Whether dashboard and `cs_auto` should share a common auth backend module immediately or in a second phase.
- Whether to return a session token now or keep the current trust model for local/demo environments.
- Whether `admin_event_logs` should keep only `actor_admin_id` or also store immutable `actor_login_id` snapshots for audit readability.
