"""Shared MySQL connection helper for the Smart Power notebooks."""

from pathlib import Path
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import URL, Engine


def get_mysql_engine(project_root: Path | None = None) -> Engine:
    """Create a SQLAlchemy engine from the git-ignored project .env file."""
    root = project_root or Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")

    required = ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing MySQL settings in .env: {', '.join(missing)}")

    url = URL.create(
        drivername="mysql+pymysql",
        username=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.environ["MYSQL_DATABASE"],
    )
    return create_engine(url, pool_pre_ping=True)


def ensure_hourly_data_schema(engine: Engine) -> None:
    """Idempotently upgrade an existing hourly_data table for carbon intensity."""
    with engine.begin() as connection:
        column_exists = connection.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'hourly_data'
              AND column_name = 'carbon_intensity_gco2_kwh'
        """)).scalar_one()
        if not column_exists:
            connection.execute(text("""
                ALTER TABLE hourly_data
                ADD COLUMN carbon_intensity_gco2_kwh DOUBLE NULL AFTER total_generation
            """))
