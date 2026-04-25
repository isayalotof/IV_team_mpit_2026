#!/usr/bin/env python3
"""
Load real Drivee data (valid.zip) into PostgreSQL.

valid.zip must contain:
  incity.csv        → anonymized_incity_orders
  pass_detail.csv   → passenger_daily_stats
  driver_detail.csv → driver_daily_stats

Usage (inside backend container):
    docker cp /path/to/valid.zip askdata-backend-1:/tmp/valid.zip
    docker cp backend/scripts/import_csv.py askdata-backend-1:/tmp/
    docker exec askdata-backend-1 python3 /tmp/import_csv.py [/tmp/valid.zip]
"""
import asyncpg
import asyncio
import zipfile
import tempfile
import os
import sys

DB_URL = "postgresql://postgres:postgres_askdata_2026@postgres:5432/drivee"
DEFAULT_PATH = "/tmp/valid.zip"

INCITY_COLUMNS = [
    "city_id", "order_id", "tender_id", "user_id", "driver_id",
    "offset_hours", "status_order", "status_tender",
    "order_timestamp", "tender_timestamp",
    "driveraccept_timestamp", "driverarrived_timestamp",
    "driverstarttheride_timestamp", "driverdone_timestamp",
    "clientcancel_timestamp", "drivercancel_timestamp",
    "order_modified_local", "cancel_before_accept_local",
    "distance_in_meters", "duration_in_seconds",
    "price_order_local", "price_tender_local", "price_start_local",
]

PASS_COLUMNS = [
    "city_id", "user_id", "order_date_part", "user_reg_date",
    "orders_count", "orders_cnt_with_tenders", "orders_cnt_accepted", "rides_count",
    "rides_time_sum_seconds", "online_time_sum_seconds", "client_cancel_after_accept",
]

DRIVER_COLUMNS = [
    "city_id", "driver_id", "tender_date_part", "driver_reg_date",
    "orders", "orders_cnt_with_tenders", "orders_cnt_accepted", "rides_count",
    "rides_time_sum_seconds", "online_time_sum_seconds", "client_cancel_after_accept",
]


async def _copy_csv(conn, table: str, columns: list[str], zip_path: str, csv_name: str) -> str:
    """Extract csv_name from zip to temp file and COPY into table. Returns asyncpg result."""
    z = zipfile.ZipFile(zip_path)
    info = z.getinfo(csv_name)
    print(f"  Extracting {csv_name} ({info.file_size / 1_000_000:.0f} MB) …")

    fd, tmp = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        with z.open(csv_name) as src, open(tmp, "wb") as dst:
            while chunk := src.read(4 << 20):  # 4 MB chunks
                dst.write(chunk)
        print(f"  Extracted {os.path.getsize(tmp) / 1_000_000:.0f} MB → {tmp}")

        with open(tmp, "rb") as f:
            result = await conn.copy_to_table(
                table,
                source=f,
                columns=columns,
                format="csv",
                header=True,
                null="",
            )
        return result
    finally:
        os.unlink(tmp)


async def load(path: str = DEFAULT_PATH) -> None:
    if not os.path.exists(path):
        print(f"ERROR: {path} not found.", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(DB_URL)

    print("Truncating all tables …")
    await conn.execute(
        "TRUNCATE anonymized_incity_orders, passenger_daily_stats, driver_daily_stats, cities"
    )

    print("\n[1/3] Loading incity.csv → anonymized_incity_orders …")
    r = await _copy_csv(conn, "anonymized_incity_orders", INCITY_COLUMNS, path, "incity.csv")
    print(f"  COPY result: {r}")
    count = await conn.fetchval("SELECT COUNT(*) FROM anonymized_incity_orders")
    print(f"  Rows loaded: {count:,}")

    print("\n[2/3] Loading pass_detail.csv → passenger_daily_stats …")
    r = await _copy_csv(conn, "passenger_daily_stats", PASS_COLUMNS, path, "pass_detail.csv")
    print(f"  COPY result: {r}")
    count = await conn.fetchval("SELECT COUNT(*) FROM passenger_daily_stats")
    print(f"  Rows loaded: {count:,}")

    print("\n[3/3] Loading driver_detail.csv → driver_daily_stats …")
    r = await _copy_csv(conn, "driver_daily_stats", DRIVER_COLUMNS, path, "driver_detail.csv")
    print(f"  COPY result: {r}")
    count = await conn.fetchval("SELECT COUNT(*) FROM driver_daily_stats")
    print(f"  Rows loaded: {count:,}")

    print("\nPopulating cities from data …")
    await conn.execute("""
        INSERT INTO cities (city_id, name)
        SELECT DISTINCT city_id, 'Город ' || city_id::text
        FROM anonymized_incity_orders
        ON CONFLICT DO NOTHING
    """)
    cities = await conn.fetch("SELECT city_id, name FROM cities ORDER BY city_id")
    for row in cities:
        print(f"  city_id={row['city_id']} → {row['name']}")

    print("\nRunning ANALYZE …")
    await conn.execute("ANALYZE anonymized_incity_orders")
    await conn.execute("ANALYZE passenger_daily_stats")
    await conn.execute("ANALYZE driver_daily_stats")

    await conn.close()
    print("\nDone!")


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    asyncio.run(load(p))
