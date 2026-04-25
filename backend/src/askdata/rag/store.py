"""RAG store: vector similarity search over (question, SQL) pairs."""
import asyncio
import logging
import sqlite3
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

RAG_DB_PATH = Path("/app/meta_data/rag_store.db")
MODEL_CACHE_DIR = Path("/app/meta_data/rag_model")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model = None
_model_lock = asyncio.Lock()

SEED_EXAMPLES: list[tuple[str, str]] = [
    (
        "отмены по городам за прошлую неделю",
        "SELECT COALESCE(c.name, o.city_id::text) AS city, "
        "COUNT(DISTINCT CASE WHEN o.clientcancel_timestamp IS NOT NULL THEN o.order_id END) AS client_cancels, "
        "COUNT(DISTINCT CASE WHEN o.drivercancel_timestamp IS NOT NULL THEN o.order_id END) AS driver_cancels, "
        "COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END) AS total_cancels "
        "FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id "
        "WHERE o.order_timestamp >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week' "
        "AND o.order_timestamp < DATE_TRUNC('week', NOW()) "
        "GROUP BY o.city_id, c.name ORDER BY total_cancels DESC LIMIT 1000",
    ),
    (
        "сколько поездок было за последние 7 дней",
        "SELECT COUNT(*) AS trips_count FROM anonymized_incity_orders o "
        "WHERE o.status_tender = 'done' AND o.order_timestamp >= NOW() - INTERVAL '7 days'",
    ),
    (
        "выручка за вчера",
        "SELECT SUM(price_order_local) AS revenue FROM anonymized_incity_orders o "
        "WHERE o.status_tender = 'done' "
        "AND o.order_timestamp >= DATE_TRUNC('day', NOW()) - INTERVAL '1 day' "
        "AND o.order_timestamp < DATE_TRUNC('day', NOW())",
    ),
    (
        "сколько уникальных заказов за месяц",
        "SELECT COUNT(DISTINCT order_id) AS orders_count "
        "FROM anonymized_incity_orders o "
        "WHERE o.order_timestamp >= DATE_TRUNC('month', NOW())",
    ),
    (
        "средний чек по городам",
        "SELECT COALESCE(c.name, o.city_id::text) AS city, "
        "ROUND(AVG(price_order_local)::numeric, 2) AS avg_check "
        "FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id "
        "WHERE o.status_tender = 'done' "
        "GROUP BY o.city_id, c.name ORDER BY avg_check DESC LIMIT 1000",
    ),
    (
        "процент отмен за 30 дней",
        "SELECT ROUND(100.0 * COUNT(DISTINCT CASE WHEN o.status_order = 'cancel' THEN o.order_id END) "
        "/ NULLIF(COUNT(DISTINCT o.order_id), 0), 2) AS cancel_rate_pct "
        "FROM anonymized_incity_orders o "
        "WHERE o.order_timestamp >= NOW() - INTERVAL '30 days'",
    ),
    (
        "динамика выручки за последние 30 дней",
        "SELECT DATE_TRUNC('day', o.order_timestamp)::date AS period_date, SUM(price_order_local) AS revenue "
        "FROM anonymized_incity_orders o "
        "WHERE o.status_tender = 'done' AND o.order_timestamp >= NOW() - INTERVAL '30 days' "
        "GROUP BY 1 ORDER BY 1 LIMIT 1000",
    ),
    (
        "сравни заказы этой и прошлой недели",
        "SELECT 'эта неделя' AS period, COUNT(DISTINCT order_id) AS orders_count FROM anonymized_incity_orders o "
        "WHERE o.order_timestamp >= DATE_TRUNC('week', NOW()) "
        "UNION ALL "
        "SELECT 'прошлая неделя' AS period, COUNT(DISTINCT order_id) AS orders_count FROM anonymized_incity_orders o "
        "WHERE o.order_timestamp >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week' "
        "AND o.order_timestamp < DATE_TRUNC('week', NOW())",
    ),
    (
        "заказы по часам за сегодня",
        "SELECT EXTRACT(HOUR FROM o.order_timestamp)::int AS hour, COUNT(DISTINCT order_id) AS orders_count "
        "FROM anonymized_incity_orders o "
        "WHERE o.order_timestamp >= DATE_TRUNC('day', NOW()) GROUP BY 1 ORDER BY 1 LIMIT 24",
    ),
    (
        "распределение заказов по статусам",
        "SELECT status_order, COUNT(DISTINCT order_id) AS cnt, "
        "ROUND(COUNT(DISTINCT order_id) * 100.0 / SUM(COUNT(DISTINCT order_id)) OVER(), 1) AS pct "
        "FROM anonymized_incity_orders o GROUP BY status_order ORDER BY cnt DESC LIMIT 1000",
    ),
    (
        "средняя длительность поездки",
        "SELECT ROUND((AVG(duration_in_seconds) / 60.0)::numeric, 1) AS avg_duration_min "
        "FROM anonymized_incity_orders o "
        "WHERE o.status_tender = 'done'",
    ),
    (
        "средняя длительность поездки по городам",
        "SELECT COALESCE(c.name, o.city_id::text) AS city, "
        "ROUND((AVG(duration_in_seconds) / 60.0)::numeric, 1) AS avg_duration_min "
        "FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id "
        "WHERE o.status_tender = 'done' "
        "GROUP BY o.city_id, c.name ORDER BY avg_duration_min DESC LIMIT 1000",
    ),
    (
        "среднее время подачи водителя по городам",
        "SELECT COALESCE(c.name, o.city_id::text) AS city, "
        "ROUND((AVG(EXTRACT(EPOCH FROM (driverarrived_timestamp - driveraccept_timestamp))) / 60.0)::numeric, 1) AS avg_pickup_min "
        "FROM anonymized_incity_orders o LEFT JOIN cities c ON c.city_id = o.city_id "
        "WHERE o.driverarrived_timestamp IS NOT NULL AND o.driveraccept_timestamp IS NOT NULL "
        "GROUP BY o.city_id, c.name ORDER BY avg_pickup_min ASC LIMIT 1000",
    ),
    (
        "топ 10 водителей по выручке за неделю",
        "SELECT o.driver_id, SUM(price_order_local) AS revenue "
        "FROM anonymized_incity_orders o "
        "WHERE o.status_tender = 'done' AND o.order_timestamp >= DATE_TRUNC('week', NOW()) "
        "GROUP BY o.driver_id ORDER BY revenue DESC LIMIT 10",
    ),
    (
        "воронка заказов за 7 дней",
        "SELECT COUNT(DISTINCT order_id) AS created, "
        "COUNT(DISTINCT CASE WHEN driveraccept_timestamp IS NOT NULL THEN order_id END) AS accepted, "
        "COUNT(DISTINCT CASE WHEN driverarrived_timestamp IS NOT NULL THEN order_id END) AS arrived, "
        "COUNT(DISTINCT CASE WHEN driverstarttheride_timestamp IS NOT NULL THEN order_id END) AS started, "
        "COUNT(DISTINCT CASE WHEN driverdone_timestamp IS NOT NULL THEN order_id END) AS completed "
        "FROM anonymized_incity_orders o WHERE o.order_timestamp >= NOW() - INTERVAL '7 days'",
    ),
    (
        "сколько уникальных клиентов было в этом месяце",
        "SELECT COUNT(DISTINCT user_id) AS unique_clients FROM anonymized_incity_orders o "
        "WHERE o.order_timestamp >= DATE_TRUNC('month', NOW())",
    ),
    (
        "сколько активных водителей на прошлой неделе",
        "SELECT COUNT(DISTINCT driver_id) AS active_drivers FROM anonymized_incity_orders o "
        "WHERE o.status_tender = 'done' "
        "AND o.order_timestamp >= DATE_TRUNC('week', NOW()) - INTERVAL '1 week' "
        "AND o.order_timestamp < DATE_TRUNC('week', NOW())",
    ),
    (
        "средняя дистанция поездки по дням недели",
        "SELECT EXTRACT(DOW FROM o.order_timestamp)::int AS day_of_week, "
        "ROUND((AVG(distance_in_meters) / 1000.0)::numeric, 2) AS avg_distance_km "
        "FROM anonymized_incity_orders o WHERE o.status_tender = 'done' "
        "GROUP BY 1 ORDER BY 1 LIMIT 7",
    ),
    (
        "отмены клиентом за 30 дней",
        "SELECT COUNT(DISTINCT order_id) AS client_cancels "
        "FROM anonymized_incity_orders o "
        "WHERE o.clientcancel_timestamp IS NOT NULL AND o.order_timestamp >= NOW() - INTERVAL '30 days'",
    ),
    (
        "топ 10 водителей по числу поездок",
        "SELECT o.driver_id, COUNT(*) AS trips_count "
        "FROM anonymized_incity_orders o "
        "WHERE o.status_tender = 'done' "
        "GROUP BY o.driver_id ORDER BY trips_count DESC LIMIT 10",
    ),
]


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _model = SentenceTransformer(MODEL_NAME, cache_folder=str(MODEL_CACHE_DIR))
        logger.info("RAG: embedding model loaded (%s)", MODEL_NAME)
    return _model


def _embed(text: str) -> np.ndarray:
    return _get_model().encode(text, normalize_embeddings=True).astype(np.float32)


def _init_db() -> None:
    RAG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(RAG_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rag_examples (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            question    TEXT    NOT NULL,
            sql         TEXT    NOT NULL,
            embedding   BLOB    NOT NULL,
            source      TEXT    DEFAULT 'manual',
            confidence  REAL    DEFAULT 1.0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def seed_if_empty() -> None:
    _init_db()
    conn = sqlite3.connect(str(RAG_DB_PATH))
    count = conn.execute("SELECT COUNT(*) FROM rag_examples").fetchone()[0]
    conn.close()
    if count > 0:
        return
    logger.info("RAG: seeding %d initial examples", len(SEED_EXAMPLES))
    for question, sql in SEED_EXAMPLES:
        try:
            add_example(question, sql, source="seed")
        except Exception as e:
            logger.warning("RAG seed failed for '%s': %s", question[:40], e)
    logger.info("RAG: seed complete")


def add_example(question: str, sql: str, source: str = "manual", confidence: float = 1.0) -> int:
    _init_db()
    # Dedup: skip if a very similar question already exists (cosine >= 0.92)
    try:
        similar = get_similar(question, top_k=1, min_score=0.92)
        if similar:
            return similar[0]["id"]
    except Exception:
        pass
    emb = _embed(question)
    conn = sqlite3.connect(str(RAG_DB_PATH))
    cur = conn.execute(
        "INSERT INTO rag_examples (question, sql, embedding, source, confidence) VALUES (?,?,?,?,?)",
        (question, sql, emb.tobytes(), source, confidence),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_similar(question: str, top_k: int = 4, min_score: float = 0.55) -> list[dict]:
    _init_db()
    try:
        q_emb = _embed(question)
    except Exception:
        return []

    conn = sqlite3.connect(str(RAG_DB_PATH))
    rows = conn.execute("SELECT id, question, sql, embedding FROM rag_examples").fetchall()
    conn.close()

    if not rows:
        return []

    scored = []
    for row_id, q, sql, emb_bytes in rows:
        emb = np.frombuffer(emb_bytes, dtype=np.float32).copy()
        score = float(np.dot(q_emb, emb))
        if score >= min_score:
            scored.append({"id": row_id, "question": q, "sql": sql, "score": round(score, 3)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def list_examples(limit: int = 200) -> list[dict]:
    _init_db()
    conn = sqlite3.connect(str(RAG_DB_PATH))
    rows = conn.execute(
        "SELECT id, question, sql, source, confidence, created_at FROM rag_examples "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "question": r[1], "sql": r[2], "source": r[3], "confidence": r[4], "created_at": r[5]}
        for r in rows
    ]


def delete_example(example_id: int) -> bool:
    _init_db()
    conn = sqlite3.connect(str(RAG_DB_PATH))
    cur = conn.execute("DELETE FROM rag_examples WHERE id = ?", (example_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def count_examples() -> int:
    _init_db()
    conn = sqlite3.connect(str(RAG_DB_PATH))
    c = conn.execute("SELECT COUNT(*) FROM rag_examples").fetchone()[0]
    conn.close()
    return c


def count_by_source() -> dict:
    _init_db()
    conn = sqlite3.connect(str(RAG_DB_PATH))
    rows = conn.execute("SELECT source, COUNT(*) FROM rag_examples GROUP BY source").fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}
