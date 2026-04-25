#!/usr/bin/env python3
"""Generate demo data for AskData (all 3 tables: anonymized_incity_orders, driver_daily_stats, passenger_daily_stats).

Cities match real Drivee data: 50, 60, 76.
"""
import asyncpg
import asyncio
import random
import uuid
from datetime import datetime, timedelta, date, timezone
from collections import defaultdict

DB_URL = "postgresql://postgres:postgres_askdata_2026@postgres:5432/drivee"
DAYS_BACK = 180
N_ORDERS = 80000

# city_id, name, weight, offset_hours, base_price, price_per_km
# Using real city_ids from valid.zip: 50, 60, 76
CITIES = [
    (50, "Город 50", 0.45, 9, 120, 10.0),
    (60, "Город 60", 0.35, 9, 110,  9.5),
    (76, "Город 76", 0.20, 9,  95,  8.5),
]

CANCEL_RATE = {50: 0.14, 60: 0.16, 76: 0.18}
DRIVER_CANCEL_SHARE = 0.45


def rush_weight(hour: int) -> float:
    if 7 <= hour <= 9:   return 2.5
    if 17 <= hour <= 20: return 2.8
    if 12 <= hour <= 14: return 1.4
    if 0 <= hour <= 5:   return 0.3
    return 1.0


def dow_weight(dow: int) -> float:
    return {0: 1.1, 1: 1.0, 2: 1.0, 3: 1.05, 4: 1.2, 5: 1.5, 6: 1.3}.get(dow, 1.0)


def random_timestamp(base: datetime, min_sec: int, max_sec: int) -> datetime:
    return base + timedelta(seconds=random.randint(min_sec, max_sec))


def gen_order(city_id: int, offset_hours: int, base_price: float, price_per_km: float,
              cancel_rate: float, now: datetime) -> dict:
    days_ago = random.expovariate(1 / (DAYS_BACK / 3))
    days_ago = min(days_ago, DAYS_BACK)

    for _ in range(10):
        hour = random.randint(0, 23)
        if random.random() < rush_weight(hour) / 2.8:
            break
    minute = random.randint(0, 59)
    second = random.randint(0, 59)

    order_ts = now - timedelta(days=days_ago)
    order_ts = order_ts.replace(hour=hour, minute=minute, second=second, microsecond=0)

    if random.random() > dow_weight(order_ts.weekday()) / 1.5:
        order_ts = order_ts - timedelta(days=random.randint(0, 2))

    order_id = str(uuid.uuid4())
    tender_id = str(uuid.uuid4())
    user_id = f"u_{random.randint(1, 15000):05d}"
    driver_id = f"d_{random.randint(1, 500):04d}"
    tender_ts = random_timestamp(order_ts, 1, 5)

    cancel_roll = random.random()
    is_cancelled = cancel_roll < cancel_rate
    is_driver_cancel = is_cancelled and (random.random() < DRIVER_CANCEL_SHARE)
    is_client_cancel = is_cancelled and not is_driver_cancel

    if is_client_cancel:
        cancel_before_accept = random.random() < 0.7
        if cancel_before_accept:
            clientcancel_ts = random_timestamp(tender_ts, 10, 120)
            return {
                "city_id": city_id, "offset_hours": offset_hours,
                "order_id": order_id, "tender_id": tender_id,
                "user_id": user_id, "driver_id": None,
                "status_order": "cancel", "status_tender": "cancel",
                "order_timestamp": order_ts, "tender_timestamp": tender_ts,
                "driveraccept_timestamp": None, "driverarrived_timestamp": None,
                "driverstarttheride_timestamp": None, "driverdone_timestamp": None,
                "clientcancel_timestamp": clientcancel_ts, "drivercancel_timestamp": None,
                "order_modified_local": clientcancel_ts, "cancel_before_accept_local": clientcancel_ts,
                "distance_in_meters": None, "duration_in_seconds": None,
                "price_order_local": None, "price_tender_local": None, "price_start_local": None,
            }
        else:
            accept_ts = random_timestamp(tender_ts, 30, 120)
            clientcancel_ts = random_timestamp(accept_ts, 30, 300)
            return {
                "city_id": city_id, "offset_hours": offset_hours,
                "order_id": order_id, "tender_id": tender_id,
                "user_id": user_id, "driver_id": driver_id,
                "status_order": "cancel", "status_tender": "accept",
                "order_timestamp": order_ts, "tender_timestamp": tender_ts,
                "driveraccept_timestamp": accept_ts, "driverarrived_timestamp": None,
                "driverstarttheride_timestamp": None, "driverdone_timestamp": None,
                "clientcancel_timestamp": clientcancel_ts, "drivercancel_timestamp": None,
                "order_modified_local": clientcancel_ts, "cancel_before_accept_local": None,
                "distance_in_meters": None, "duration_in_seconds": None,
                "price_order_local": None, "price_tender_local": None, "price_start_local": None,
            }

    if is_driver_cancel:
        accept_ts = random_timestamp(tender_ts, 30, 120)
        drivercancel_ts = random_timestamp(accept_ts, 30, 180)
        return {
            "city_id": city_id, "offset_hours": offset_hours,
            "order_id": order_id, "tender_id": tender_id,
            "user_id": user_id, "driver_id": driver_id,
            "status_order": "cancel", "status_tender": "cancel",
            "order_timestamp": order_ts, "tender_timestamp": tender_ts,
            "driveraccept_timestamp": accept_ts, "driverarrived_timestamp": None,
            "driverstarttheride_timestamp": None, "driverdone_timestamp": None,
            "clientcancel_timestamp": None, "drivercancel_timestamp": drivercancel_ts,
            "order_modified_local": drivercancel_ts, "cancel_before_accept_local": None,
            "distance_in_meters": None, "duration_in_seconds": None,
            "price_order_local": None, "price_tender_local": None, "price_start_local": None,
        }

    # Completed trip
    accept_ts = random_timestamp(tender_ts, 30, 120)
    arrived_ts = random_timestamp(accept_ts, 180, 600)
    start_ts = random_timestamp(arrived_ts, 0, 120)
    distance_m = max(1500, min(50000, int(random.gauss(8000, 4000))))
    speed_mps = random.uniform(6, 12)
    duration_s = max(300, int(distance_m / speed_mps + random.gauss(0, 60)))
    done_ts = start_ts + timedelta(seconds=duration_s)
    price = round(max(50, base_price + (distance_m / 1000.0) * price_per_km + random.gauss(0, 20)), 2)
    price_tender = round(price * random.uniform(0.95, 1.05), 2)

    return {
        "city_id": city_id, "offset_hours": offset_hours,
        "order_id": order_id, "tender_id": tender_id,
        "user_id": user_id, "driver_id": driver_id,
        "status_order": "done", "status_tender": "done",
        "order_timestamp": order_ts, "tender_timestamp": tender_ts,
        "driveraccept_timestamp": accept_ts, "driverarrived_timestamp": arrived_ts,
        "driverstarttheride_timestamp": start_ts, "driverdone_timestamp": done_ts,
        "clientcancel_timestamp": None, "drivercancel_timestamp": None,
        "order_modified_local": done_ts, "cancel_before_accept_local": None,
        "distance_in_meters": distance_m, "duration_in_seconds": duration_s,
        "price_order_local": price, "price_tender_local": price_tender,
        "price_start_local": round(base_price, 2),
    }


def build_driver_daily_stats(orders: list[dict]) -> list[dict]:
    """Aggregate orders into driver_daily_stats rows."""
    # driver_reg_date: assign random past date per driver
    driver_reg = {}

    agg: dict[tuple, dict] = defaultdict(lambda: {
        "orders": 0, "with_tenders": 0, "accepted": 0, "rides": 0,
        "rides_time": 0.0, "online_time": 0.0, "client_cancel_after_accept": 0,
    })

    for o in orders:
        if not o.get("driver_id"):
            continue
        driver_id = o["driver_id"]
        city_id = o["city_id"]
        day = o["order_timestamp"].date()
        key = (city_id, driver_id, day)

        if driver_id not in driver_reg:
            driver_reg[driver_id] = day - timedelta(days=random.randint(30, 730))

        a = agg[key]
        a["orders"] += 1
        if o.get("tender_id"):
            a["with_tenders"] += 1
        if o.get("driveraccept_timestamp"):
            a["accepted"] += 1
        if o["status_tender"] == "done":
            a["rides"] += 1
            dur = o.get("duration_in_seconds") or 0
            a["rides_time"] += dur
        if o.get("clientcancel_timestamp") and o.get("driveraccept_timestamp"):
            a["client_cancel_after_accept"] += 1

    rows = []
    for (city_id, driver_id, day), a in agg.items():
        online_h = a["rides_time"] * random.uniform(1.5, 3.0)
        rows.append({
            "city_id": city_id,
            "driver_id": driver_id,
            "tender_date_part": day,
            "driver_reg_date": driver_reg.get(driver_id, day - timedelta(days=90)),
            "orders": a["orders"],
            "orders_cnt_with_tenders": a["with_tenders"],
            "orders_cnt_accepted": a["accepted"],
            "rides_count": a["rides"],
            "rides_time_sum_seconds": round(a["rides_time"], 2),
            "online_time_sum_seconds": round(online_h, 2),
            "client_cancel_after_accept": a["client_cancel_after_accept"],
        })
    return rows


def build_passenger_daily_stats(orders: list[dict]) -> list[dict]:
    """Aggregate orders into passenger_daily_stats rows."""
    user_reg = {}

    agg: dict[tuple, dict] = defaultdict(lambda: {
        "orders": 0, "with_tenders": 0, "accepted": 0, "rides": 0,
        "rides_time": 0.0, "online_time": 0.0, "client_cancel_after_accept": 0,
    })

    for o in orders:
        user_id = o["user_id"]
        city_id = o["city_id"]
        day = o["order_timestamp"].date()
        key = (city_id, user_id, day)

        if user_id not in user_reg:
            user_reg[user_id] = day - timedelta(days=random.randint(0, 730))

        a = agg[key]
        a["orders"] += 1
        if o.get("tender_id"):
            a["with_tenders"] += 1
        if o.get("driveraccept_timestamp"):
            a["accepted"] += 1
        if o["status_tender"] == "done":
            a["rides"] += 1
            dur = o.get("duration_in_seconds") or 0
            a["rides_time"] += dur
            a["online_time"] += dur * random.uniform(1.0, 1.5)
        if o.get("clientcancel_timestamp") and o.get("driveraccept_timestamp"):
            a["client_cancel_after_accept"] += 1

    rows = []
    for (city_id, user_id, day), a in agg.items():
        rows.append({
            "city_id": city_id,
            "user_id": user_id,
            "order_date_part": day,
            "user_reg_date": user_reg.get(user_id, day - timedelta(days=180)),
            "orders_count": a["orders"],
            "orders_cnt_with_tenders": a["with_tenders"],
            "orders_cnt_accepted": a["accepted"],
            "rides_count": a["rides"],
            "rides_time_sum_seconds": round(a["rides_time"], 2),
            "online_time_sum_seconds": round(a["online_time"], 2),
            "client_cancel_after_accept": a["client_cancel_after_accept"],
        })
    return rows


async def seed():
    conn = await asyncpg.connect(DB_URL)

    print("Truncating tables...")
    await conn.execute(
        "TRUNCATE anonymized_incity_orders, passenger_daily_stats, driver_daily_stats, cities"
    )

    print("Inserting cities...")
    for city_id, name, *_ in CITIES:
        await conn.execute(
            "INSERT INTO cities (city_id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            city_id, name,
        )

    print(f"Generating {N_ORDERS} orders...")
    now = datetime.now(tz=timezone.utc)

    city_weights = [c[2] for c in CITIES]
    city_total = sum(city_weights)
    city_probs = [w / city_total for w in city_weights]

    all_orders: list[dict] = []
    batch: list[dict] = []
    BATCH_SIZE = 2000

    for i in range(N_ORDERS):
        city_idx = random.choices(range(len(CITIES)), weights=city_probs)[0]
        city_id, _, _, offset_hours, base_price, price_per_km = CITIES[city_idx]
        cancel_rate = CANCEL_RATE[city_id]
        row = gen_order(city_id, offset_hours, base_price, price_per_km, cancel_rate, now)
        batch.append(row)
        all_orders.append(row)

        if len(batch) >= BATCH_SIZE or i == N_ORDERS - 1:
            await conn.executemany(
                """
                INSERT INTO anonymized_incity_orders (
                    city_id, order_id, tender_id, user_id, driver_id, offset_hours,
                    status_order, status_tender,
                    order_timestamp, tender_timestamp, driveraccept_timestamp,
                    driverarrived_timestamp, driverstarttheride_timestamp, driverdone_timestamp,
                    clientcancel_timestamp, drivercancel_timestamp,
                    order_modified_local, cancel_before_accept_local,
                    distance_in_meters, duration_in_seconds,
                    price_order_local, price_tender_local, price_start_local
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23
                )
                """,
                [
                    (
                        r["city_id"], r["order_id"], r["tender_id"],
                        r["user_id"], r["driver_id"], r["offset_hours"],
                        r["status_order"], r["status_tender"],
                        r["order_timestamp"], r["tender_timestamp"], r["driveraccept_timestamp"],
                        r["driverarrived_timestamp"], r["driverstarttheride_timestamp"], r["driverdone_timestamp"],
                        r["clientcancel_timestamp"], r["drivercancel_timestamp"],
                        r["order_modified_local"], r["cancel_before_accept_local"],
                        r["distance_in_meters"], r["duration_in_seconds"],
                        r["price_order_local"], r["price_tender_local"], r["price_start_local"],
                    )
                    for r in batch
                ],
            )
            print(f"  anonymized_incity_orders: {i + 1}/{N_ORDERS}")
            batch.clear()

    print("Building driver_daily_stats...")
    driver_rows = build_driver_daily_stats(all_orders)
    BATCH_SIZE = 1000
    for i in range(0, len(driver_rows), BATCH_SIZE):
        chunk = driver_rows[i:i + BATCH_SIZE]
        await conn.executemany(
            """INSERT INTO driver_daily_stats (
                city_id, driver_id, tender_date_part, driver_reg_date,
                orders, orders_cnt_with_tenders, orders_cnt_accepted, rides_count,
                rides_time_sum_seconds, online_time_sum_seconds, client_cancel_after_accept
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
            [(r["city_id"], r["driver_id"], r["tender_date_part"], r["driver_reg_date"],
              r["orders"], r["orders_cnt_with_tenders"], r["orders_cnt_accepted"], r["rides_count"],
              r["rides_time_sum_seconds"], r["online_time_sum_seconds"], r["client_cancel_after_accept"])
             for r in chunk],
        )
    print(f"  driver_daily_stats: {len(driver_rows)} rows")

    print("Building passenger_daily_stats...")
    pass_rows = build_passenger_daily_stats(all_orders)
    for i in range(0, len(pass_rows), BATCH_SIZE):
        chunk = pass_rows[i:i + BATCH_SIZE]
        await conn.executemany(
            """INSERT INTO passenger_daily_stats (
                city_id, user_id, order_date_part, user_reg_date,
                orders_count, orders_cnt_with_tenders, orders_cnt_accepted, rides_count,
                rides_time_sum_seconds, online_time_sum_seconds, client_cancel_after_accept
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
            [(r["city_id"], r["user_id"], r["order_date_part"], r["user_reg_date"],
              r["orders_count"], r["orders_cnt_with_tenders"], r["orders_cnt_accepted"], r["rides_count"],
              r["rides_time_sum_seconds"], r["online_time_sum_seconds"], r["client_cancel_after_accept"])
             for r in chunk],
        )
    print(f"  passenger_daily_stats: {len(pass_rows)} rows")

    print("Running ANALYZE...")
    await conn.execute("ANALYZE anonymized_incity_orders")
    await conn.execute("ANALYZE driver_daily_stats")
    await conn.execute("ANALYZE passenger_daily_stats")
    await conn.close()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
