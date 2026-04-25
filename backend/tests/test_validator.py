"""Tests for SQL validator."""
import pytest
from askdata.query.validator import validate_sql

WHITELIST = [
    "anonymized_incity_orders",
    "passenger_daily_stats",
    "driver_daily_stats",
    "cities",
]


def test_valid_select():
    sql = "SELECT city_id, COUNT(*) FROM anonymized_incity_orders GROUP BY city_id"
    result = validate_sql(sql, WHITELIST)
    assert result.ok


def test_auto_limit():
    sql = "SELECT * FROM anonymized_incity_orders"
    result = validate_sql(sql, WHITELIST)
    assert result.ok
    assert "LIMIT" in result.sql.upper()


def test_rejects_delete():
    sql = "DELETE FROM anonymized_incity_orders WHERE order_id = '123'"
    result = validate_sql(sql, WHITELIST)
    assert not result.ok


def test_rejects_drop():
    sql = "DROP TABLE anonymized_incity_orders"
    result = validate_sql(sql, WHITELIST)
    assert not result.ok


def test_rejects_unknown_table():
    sql = "SELECT * FROM secret_table"
    result = validate_sql(sql, WHITELIST)
    assert not result.ok
    assert "table_not_in_whitelist" in " ".join(result.violations)


def test_rejects_old_table_name():
    sql = "SELECT * FROM orders"
    result = validate_sql(sql, WHITELIST)
    assert not result.ok
    assert "table_not_in_whitelist" in " ".join(result.violations)


def test_rejects_system_schema():
    sql = "SELECT * FROM pg_catalog.pg_tables"
    result = validate_sql(sql, WHITELIST)
    assert not result.ok


def test_rejects_banned_function():
    sql = "SELECT pg_sleep(5)"
    result = validate_sql(sql, WHITELIST)
    assert not result.ok


def test_valid_join_incity_cities():
    sql = (
        "SELECT c.name, COUNT(DISTINCT o.order_id) AS cnt "
        "FROM anonymized_incity_orders o "
        "LEFT JOIN cities c ON c.city_id = o.city_id "
        "GROUP BY c.name"
    )
    result = validate_sql(sql, WHITELIST)
    assert result.ok


def test_valid_driver_daily_stats():
    sql = (
        "SELECT driver_id, SUM(rides_count) AS total_rides "
        "FROM driver_daily_stats "
        "GROUP BY driver_id ORDER BY total_rides DESC LIMIT 10"
    )
    result = validate_sql(sql, WHITELIST)
    assert result.ok


def test_valid_passenger_daily_stats():
    sql = (
        "SELECT user_reg_date, COUNT(DISTINCT user_id) AS new_users "
        "FROM passenger_daily_stats "
        "GROUP BY user_reg_date ORDER BY user_reg_date"
    )
    result = validate_sql(sql, WHITELIST)
    assert result.ok


def test_valid_subquery():
    sql = (
        "SELECT * FROM ("
        "SELECT city_id, COUNT(DISTINCT order_id) AS cnt "
        "FROM anonymized_incity_orders GROUP BY city_id"
        ") t WHERE cnt > 10"
    )
    result = validate_sql(sql, WHITELIST)
    assert result.ok


def test_valid_cte():
    sql = """
    WITH stats AS (
        SELECT city_id, COUNT(DISTINCT order_id) AS cnt
        FROM anonymized_incity_orders GROUP BY city_id
    )
    SELECT * FROM stats ORDER BY cnt DESC
    """
    result = validate_sql(sql, WHITELIST)
    assert result.ok


def test_sql_injection_attempt():
    sql = "SELECT * FROM anonymized_incity_orders WHERE city_id = 60; DROP TABLE anonymized_incity_orders; --"
    result = validate_sql(sql, WHITELIST)
    assert not result.ok or "DROP" not in result.sql.upper()


def test_valid_cross_table_query():
    sql = (
        "SELECT d.driver_id, d.rides_count, COUNT(DISTINCT o.order_id) AS orders "
        "FROM driver_daily_stats d "
        "JOIN anonymized_incity_orders o ON o.driver_id = d.driver_id "
        "GROUP BY d.driver_id, d.rides_count LIMIT 100"
    )
    result = validate_sql(sql, WHITELIST)
    assert result.ok
