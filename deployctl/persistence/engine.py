"""Async SQLAlchemy engine and session factory for deployctl.

This is the entry point for the first stateful slice. It mirrors the runtime
configuration already defined in `deployctl.app.config.Config` and gives the
persistence layer a single place to own async engine/session bootstrapping.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deployctl.app.config import Config


def create_engine(config: Config) -> create_async_engine:
    """Create the async SQLAlchemy engine for the configured database."""
    return create_async_engine(config.database_url)


def create_session_factory(
    engine: create_async_engine,
) -> async_sessionmaker:
    """Create an async session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
