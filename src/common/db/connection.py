"""Database connection helpers shared by application workflows."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


load_dotenv()


class DatabaseSettings(BaseModel):
    """PostgreSQL settings loaded from environment variables."""

    model_config = ConfigDict(frozen=True)

    host: str = Field(default_factory=lambda: os.environ["DB_HOST"])
    port: int = Field(default_factory=lambda: int(os.environ["DB_PORT"]))
    user: str = Field(default_factory=lambda: os.environ["DB_USER"])
    password: str = Field(default_factory=lambda: os.environ["DB_PASSWORD"])
    dbname: str = Field(default_factory=lambda: os.environ["DB_NAME"])
    connect_timeout: int = Field(default_factory=lambda: int(os.environ.get("DB_CONNECT_TIMEOUT", "15")))


@contextmanager
def db_connection(settings: DatabaseSettings | None = None) -> Iterator[psycopg.Connection]:
    """Open a PostgreSQL connection using environment-backed settings."""

    db_settings = settings or DatabaseSettings()
    with psycopg.connect(
        host=db_settings.host,
        port=db_settings.port,
        user=db_settings.user,
        password=db_settings.password,
        dbname=db_settings.dbname,
        connect_timeout=db_settings.connect_timeout,
    ) as conn:
        yield conn
