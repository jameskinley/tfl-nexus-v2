from sqlalchemy import text
from logging import getLogger
from dateutil import parser

logger = getLogger(__name__)


def upgrade_timestamp_columns(engine):
    """Ensure timestamp-like columns are stored as SQL TIMESTAMP in Postgres.

    For each target (table, column) this function:
    - checks the column type in information_schema
    - if it's a varchar/text, attempts a single `ALTER COLUMN ... TYPE timestamp USING ...`
    - if that fails, falls back to adding a temporary timestamp column, parsing
      values in Python and updating rows individually, then replacing the column.

    This is defensive and avoids dropping tables or requiring manual SQL.
    """
    targets = [
        ("network_reports", "timestamp"),
        ("disruption_events", "timestamp"),
        ("station_crowding", "timestamp"),
        ("polling_meta", "last_poll_timestamp"),
    ]

    with engine.begin() as conn:
        for table, col in targets:
            info = conn.execute(
                text(
                    "SELECT data_type, udt_name FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": col},
            ).mappings().first()

            if not info:
                logger.debug("Skipping %s.%s - column not present", table, col)
                continue

            data_type = info.get("data_type") or ""
            udt = info.get("udt_name") or ""

            if data_type in ("character varying", "text") or udt in ("varchar", "text"):
                logger.info("Upgrading %s.%s from %s/%s to timestamp", table, col, data_type, udt)
                try:
                    # Try a direct, single-statement ALTER which is fastest when values cast cleanly
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE timestamp USING NULLIF({col}, '')::timestamp"
                        )
                    )
                    logger.info("Direct ALTER succeeded for %s.%s", table, col)
                    continue
                except Exception as ex:
                    logger.warning("Direct ALTER failed for %s.%s: %s", table, col, ex)

                # Fallback: add temp column and populate row-by-row with safe parsing
                tmp_col = f"__tmp_{col}"
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {tmp_col} timestamp"))

                rows = conn.execute(text(f"SELECT id, {col} FROM {table}")).mappings().all()
                for r in rows:
                    pk = r.get("id")
                    raw = r.get(col)
                    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
                        parsed = None
                    else:
                        try:
                            parsed = parser.parse(raw) if not isinstance(raw, (bytes, bytearray)) else None
                        except Exception:
                            parsed = None

                    conn.execute(
                        text(f"UPDATE {table} SET {tmp_col} = :p WHERE id = :id"),
                        {"p": parsed, "id": pk},
                    )

                # Replace column: drop old, rename tmp
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {col}"))
                conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN {tmp_col} TO {col}"))
                logger.info("Replaced column %s.%s with timestamp values (parsed).", table, col)
            else:
                logger.debug("Column %s.%s already type %s (%s)", table, col, data_type, udt)
