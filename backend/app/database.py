"""Database connection: Neon Postgres, configured with the DATABASE_URL environment variable
(from .env when running locally, from the project settings on Vercel)."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ON_SERVERLESS = bool(os.getenv("VERCEL"))


def _make_engine():
    if not DATABASE_URL:
        return None  # create_app() reports the missing setting with a clear message
    # Use the psycopg 3 driver for postgres:// and postgresql:// URLs.
    url = DATABASE_URL.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
    if ON_SERVERLESS:
        # Serverless functions are frozen between requests, so don't keep connections around;
        # Neon's pooled (-pooler) endpoint does the pooling instead.
        return create_engine(url, poolclass=NullPool)
    # Neon scales to zero after 5 idle minutes; check connections before reuse.
    return create_engine(url, pool_pre_ping=True, pool_recycle=240, pool_size=5)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass
