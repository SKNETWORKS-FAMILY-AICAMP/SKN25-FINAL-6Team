from __future__ import annotations

import os
import random
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

DB_HOST = "100.97.235.15"
DB_PORT = "5432"
DB_USER = "game_cs_user"
DB_NAME = "game_cs"

RNG_SEED = 20260526

TARGETS = {
    "community_users": 630,
    "game_accounts": 630,
    "qa_ticket": 950,
    "payments": 320,
    "refunds": 55,
    "item_delivery_logs": 140,
    "gacha_logs": 180,
}

TARGET_TABLES = [
    "refunds",
    "item_delivery_logs",
    "gacha_logs",
    "payments",
    "qa_ticket",
    "game_accounts",
    "community_users",
]

ID_COLUMNS = {
    "community_users": "user_id",
    "game_accounts": "account_id",
    "qa_ticket": "ticket_id",
    "payments": "payment_id",
    "refunds": "refund_id",
    "item_delivery_logs": "delivery_id",
    "gacha_logs": "gacha_id",
}


def _load_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH)


def _connect() -> psycopg.Connection:
    password = os.environ.get("DB_PASSWORD")
    if not password:
        raise RuntimeError("DB_PASSWORD environment variable is required")
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=password,
        dbname=DB_NAME,
        connect_timeout=15,
        row_factory=dict_row,
    )


def _fetch_all(cur: psycopg.Cursor, table_name: str) -> list[dict]:
    cur.execute(f"SELECT * FROM public.{table_name} ORDER BY 1")
    return list(cur.fetchall())


def _pick_selected_accounts(
    accounts_ex: list[dict],
    tickets_ex: list[dict],
    target_count: int,
    rng: random.Random,
) -> list[dict]:
    ticket_counts = Counter(ticket["user_id"] for ticket in tickets_ex)
    scored_accounts = []
    for row in accounts_ex:
        score = ticket_counts.get(row["user_id"], 0)
        scored_accounts.append((score, rng.random(), row))
    scored_accounts.sort(key=lambda item: (-item[0], item[1], item[2]["account_id"]))
    return [row for _, _, row in scored_accounts[:target_count]]


def _sample_tickets_for_accounts(
    tickets_ex: list[dict],
    selected_user_ids: set[int],
    selected_account_ids: set[int],
    target_count: int,
    rng: random.Random,
) -> list[dict]:
    null_ratio = sum(1 for row in tickets_ex if row["account_id"] is None) / max(len(tickets_ex), 1)
    target_null_count = round(target_count * null_ratio)

    null_pool = [
        row
        for row in tickets_ex
        if row["user_id"] in selected_user_ids and row["account_id"] is None
    ]
    nonnull_pool = [
        row
        for row in tickets_ex
        if row["user_id"] in selected_user_ids and row["account_id"] in selected_account_ids
    ]

    if len(nonnull_pool) + len(null_pool) < target_count:
        raise RuntimeError("Not enough qa_ticket_ex rows for the selected user/account set")

    sampled_null = rng.sample(null_pool, min(target_null_count, len(null_pool)))
    sampled_nonnull = rng.sample(nonnull_pool, target_count - len(sampled_null))
    sampled = sampled_null + sampled_nonnull
    rng.shuffle(sampled)
    return sampled


def _choose_templates(rows: list[dict], target_count: int, rng: random.Random) -> list[dict]:
    return [dict(rng.choice(rows)) for _ in range(target_count)]


def _next_base(rows: list[dict], key: str, fallback: int) -> int:
    return max((int(row[key]) for row in rows), default=fallback) + 1


def _random_time(
    rng: random.Random,
    start: datetime,
    end: datetime,
) -> datetime:
    delta = end - start
    seconds = int(delta.total_seconds())
    return start + timedelta(seconds=rng.randint(0, max(seconds, 1)))


def _build_payments(
    templates: list[dict],
    selected_accounts: list[dict],
    payments_ex: list[dict],
    rng: random.Random,
) -> list[dict]:
    selected_account_ids = [row["account_id"] for row in selected_accounts]
    next_payment_id = _next_base(payments_ex, "payment_id", 7000)
    base_start = datetime(2026, 4, 1, 9, 0, 0)
    base_end = datetime(2026, 5, 25, 22, 0, 0)
    rows: list[dict] = []
    for idx, template in enumerate(templates):
        paid_at = _random_time(rng, base_start, base_end)
        payment_id = next_payment_id + idx
        payment_method = template["payment_method"] or rng.choice(["card", "mobile", "store_credit", "google_pay"])
        payment_status = template["payment_status"] or rng.choice(["paid", "pending", "fail", "success"])
        rows.append(
            {
                "payment_id": payment_id,
                "account_id": rng.choice(selected_account_ids),
                "product_name": template["product_name"],
                "product_type": template["product_type"],
                "amount": Decimal(template["amount"] or 0),
                "currency": template["currency"] or "KRW",
                "payment_method": payment_method,
                "payment_status": payment_status,
                "transaction_id": f"TXN{payment_id:08d}",
                "paid_at": paid_at,
            }
        )
    return rows


def _build_refunds(
    templates: list[dict],
    payments: list[dict],
    refunds_ex: list[dict],
    rng: random.Random,
) -> list[dict]:
    refundable_payments = rng.sample(payments, min(len(payments), len(templates)))
    next_refund_id = _next_base(refunds_ex, "refund_id", 9500)
    rows: list[dict] = []
    for idx, (template, payment) in enumerate(zip(templates, refundable_payments)):
        requested_at = payment["paid_at"] + timedelta(minutes=rng.randint(5, 1440))
        processed_at = None
        status = template["refund_status"] or "pending"
        if status in {"approved", "completed"}:
            processed_at = requested_at + timedelta(hours=rng.randint(1, 72))
        rows.append(
            {
                "refund_id": next_refund_id + idx,
                "payment_id": payment["payment_id"],
                "refund_status": status,
                "refund_reason": template["refund_reason"],
                "requested_at": requested_at,
                "processed_at": processed_at,
            }
        )
    return rows


def _build_item_delivery_logs(
    templates: list[dict],
    payments: list[dict],
    selected_accounts: list[dict],
    delivery_ex: list[dict],
    rng: random.Random,
) -> list[dict]:
    next_delivery_id = _next_base(delivery_ex, "delivery_id", 8000)
    selected_account_ids = [row["account_id"] for row in selected_accounts]
    rows: list[dict] = []
    payment_templates = [row for row in templates if row.get("payment_id") is not None]
    event_templates = [row for row in templates if row.get("payment_id") is None]
    for idx, template in enumerate(templates):
        linked_to_payment = template in payment_templates and rng.random() < 0.75
        payment_id = None
        account_id = rng.choice(selected_account_ids)
        expected_at = _random_time(rng, datetime(2026, 4, 1, 8, 0, 0), datetime(2026, 5, 25, 23, 0, 0))
        delivered_at = None
        if linked_to_payment and payments:
            payment = rng.choice(payments)
            payment_id = payment["payment_id"]
            account_id = payment["account_id"]
            expected_at = payment["paid_at"] + timedelta(minutes=rng.randint(1, 180))
        status = template["delivery_status"]
        if status in {"delivered"}:
            delivered_at = expected_at + timedelta(minutes=rng.randint(1, 120))
        elif status == "failed":
            delivered_at = None
        elif status == "fail":
            delivered_at = None

        rows.append(
            {
                "delivery_id": next_delivery_id + idx,
                "payment_id": payment_id,
                "account_id": account_id,
                "source_type": template["source_type"] or ("event_reward" if template in event_templates else "payment"),
                "item_name": template["item_name"],
                "quantity": int(template["quantity"] or rng.randint(1, 3)),
                "delivery_status": status,
                "expected_at": expected_at,
                "delivered_at": delivered_at,
            }
        )
    return rows


def _build_gacha_logs(
    templates: list[dict],
    selected_accounts: list[dict],
    gacha_ex: list[dict],
    rng: random.Random,
) -> list[dict]:
    next_gacha_id = _next_base(gacha_ex, "gacha_id", 9000)
    selected_account_ids = [row["account_id"] for row in selected_accounts]
    rows: list[dict] = []
    for idx, template in enumerate(templates):
        rows.append(
            {
                "gacha_id": next_gacha_id + idx,
                "account_id": rng.choice(selected_account_ids),
                "banner_name": template["banner_name"],
                "item_name": template["item_name"],
                "item_type": template["item_type"],
                "rarity": template["rarity"],
                "pity_count": int(template["pity_count"] or rng.randint(0, 90)),
                "pulled_at": _random_time(rng, datetime(2026, 4, 1, 8, 0, 0), datetime(2026, 5, 25, 23, 0, 0)),
            }
        )
    return rows


def _insert_many(cur: psycopg.Cursor, table_name: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    values = [tuple(row[column] for column in columns) for row in rows]
    cur.executemany(
        f"INSERT INTO public.{table_name} ({column_sql}) VALUES ({placeholders})",
        values,
    )


def _reset_sequences(cur: psycopg.Cursor) -> None:
    for table_name, id_column in ID_COLUMNS.items():
        cur.execute(
            "SELECT pg_get_serial_sequence(%s, %s)",
            (f"public.{table_name}", id_column),
        )
        sequence_name = cur.fetchone()["pg_get_serial_sequence"]
        if not sequence_name:
            continue
        cur.execute(f"SELECT COALESCE(MAX({id_column}), 1) AS max_id FROM public.{table_name}")
        max_id = cur.fetchone()["max_id"]
        cur.execute("SELECT setval(%s, %s, true)", (sequence_name, max_id))


def main() -> None:
    _load_env()
    rng = random.Random(RNG_SEED)

    with _connect() as conn:
        with conn.cursor() as cur:
            accounts_ex = _fetch_all(cur, "game_accounts_ex")
            users_ex = _fetch_all(cur, "community_users_ex")
            tickets_ex = _fetch_all(cur, "qa_ticket_ex")
            payments_ex = _fetch_all(cur, "payments_ex")
            refunds_ex = _fetch_all(cur, "refunds_ex")
            deliveries_ex = _fetch_all(cur, "item_delivery_logs_ex")
            gacha_ex = _fetch_all(cur, "gacha_logs_ex")

            selected_accounts = _pick_selected_accounts(accounts_ex, tickets_ex, TARGETS["game_accounts"], rng)
            selected_user_ids = {row["user_id"] for row in selected_accounts}
            selected_account_ids = {row["account_id"] for row in selected_accounts}

            user_map = {row["user_id"]: row for row in users_ex}
            selected_users = [user_map[user_id] for user_id in sorted(selected_user_ids)]
            if len(selected_users) != TARGETS["community_users"]:
                raise RuntimeError("Selected user count does not match target")

            selected_tickets = _sample_tickets_for_accounts(
                tickets_ex=tickets_ex,
                selected_user_ids=selected_user_ids,
                selected_account_ids=selected_account_ids,
                target_count=TARGETS["qa_ticket"],
                rng=rng,
            )

            generated_payments = _build_payments(
                templates=_choose_templates(payments_ex, TARGETS["payments"], rng),
                selected_accounts=selected_accounts,
                payments_ex=payments_ex,
                rng=rng,
            )
            generated_refunds = _build_refunds(
                templates=_choose_templates(refunds_ex, TARGETS["refunds"], rng),
                payments=generated_payments,
                refunds_ex=refunds_ex,
                rng=rng,
            )
            generated_deliveries = _build_item_delivery_logs(
                templates=_choose_templates(deliveries_ex, TARGETS["item_delivery_logs"], rng),
                payments=generated_payments,
                selected_accounts=selected_accounts,
                delivery_ex=deliveries_ex,
                rng=rng,
            )
            generated_gacha = _build_gacha_logs(
                templates=_choose_templates(gacha_ex, TARGETS["gacha_logs"], rng),
                selected_accounts=selected_accounts,
                gacha_ex=gacha_ex,
                rng=rng,
            )

            cur.execute(
                "TRUNCATE TABLE public.refunds, public.item_delivery_logs, public.gacha_logs, public.payments, public.qa_ticket, public.game_accounts, public.community_users RESTART IDENTITY CASCADE"
            )

            _insert_many(cur, "community_users", selected_users)
            _insert_many(cur, "game_accounts", selected_accounts)
            _insert_many(cur, "qa_ticket", selected_tickets)
            _insert_many(cur, "payments", generated_payments)
            _insert_many(cur, "refunds", generated_refunds)
            _insert_many(cur, "item_delivery_logs", generated_deliveries)
            _insert_many(cur, "gacha_logs", generated_gacha)
            _reset_sequences(cur)

        conn.commit()

    print("DATASET_REPOPULATED")
    for table_name, target_count in TARGETS.items():
        print(f"{table_name}\t{target_count}")


if __name__ == "__main__":
    main()
