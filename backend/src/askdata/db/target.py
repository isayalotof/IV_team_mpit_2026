import asyncpg
from asyncpg import Pool
from askdata.config import get_settings
import re

settings = get_settings()
_pool: Pool | None = None


async def get_pool() -> Pool:
    global _pool
    if _pool is None:
        # Parse connection params from SQLAlchemy URL
        url = settings.target_db_url.replace("postgresql+asyncpg://", "postgresql://")
        _pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def execute_read_only(
    sql: str,
    timeout: float | None = None,
    max_rows: int | None = None,
    dry_run: bool = False,
) -> list[dict]:
    if timeout is None:
        timeout = settings.sql_timeout_seconds
    if max_rows is None:
        max_rows = settings.max_rows

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL statement_timeout = '{int(timeout * 1000)}ms'")
        await conn.execute("SET LOCAL default_transaction_read_only = on")
        await conn.execute("SET LOCAL lock_timeout = '5s'")

        async with conn.transaction(readonly=True):
            if dry_run:
                await conn.execute(f"EXPLAIN {sql}")
                return []
            rows = await conn.fetch(sql)
            result = [dict(row) for row in rows[:max_rows]]
            return result


async def get_schema() -> list[dict]:
    """Fetch schema info from information_schema for whitelisted tables."""
    from askdata.semantic.loader import get_semantic_layer
    sl = get_semantic_layer()
    whitelist = sl.whitelist_tables if sl else []

    pool = await get_pool()
    async with pool.acquire() as conn:
        if whitelist:
            tables_filter = "AND c.table_name = ANY($1::text[])"
            rows = await conn.fetch(
                f"""
                SELECT c.table_name, c.column_name, c.data_type, c.is_nullable
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                {tables_filter}
                ORDER BY c.table_name, c.ordinal_position
                """,
                whitelist,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT c.table_name, c.column_name, c.data_type, c.is_nullable
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                ORDER BY c.table_name, c.ordinal_position
                """
            )

    tables: dict[str, list] = {}
    for row in rows:
        tname = row["table_name"]
        if tname not in tables:
            tables[tname] = []
        tables[tname].append({
            "name": row["column_name"],
            "type": row["data_type"],
            "nullable": row["is_nullable"] == "YES",
        })

    return [{"name": t, "columns": cols} for t, cols in tables.items()]
