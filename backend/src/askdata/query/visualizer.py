TEMPORAL_TYPES = {"date", "timestamp", "timestamp without time zone", "timestamp with time zone"}
NUMERIC_TYPES = {"integer", "bigint", "numeric", "double precision", "real", "float", "int4", "int8"}

# Column names that act as x-axis even when integer type (hour, weekday, etc.)
ORDINAL_AXIS_NAMES = {"hour", "hour_of_day", "day_of_week", "weekday", "month", "week", "quarter", "year"}

# Prefer these keywords as the main metric when multiple numerics exist
METRIC_PRIORITY_KW = ("rate", "pct", "percent", "ratio", "доля", "процент")
TOTAL_PREFER_KW = ("total", "running", "cumul", "накопит")


def _is_temporal(col: dict) -> bool:
    name = col.get("name", "").lower()
    t = col.get("type", "").lower()
    return t in TEMPORAL_TYPES or "date" in name or "time" in name


def _is_ordinal_axis(col: dict) -> bool:
    """Integer column that semantically acts as an x-axis (hour, weekday, etc.)."""
    return col.get("name", "").lower() in ORDINAL_AXIS_NAMES


def _is_numeric(col: dict) -> bool:
    t = col.get("type", "").lower()
    return t in NUMERIC_TYPES or t.startswith("numeric")


def _is_categorical(col: dict) -> bool:
    return not _is_temporal(col) and not _is_numeric(col)


def _best_y(num_cols: list[dict]) -> dict:
    """Pick the most meaningful numeric column as y-axis."""
    # 1. Prefer rate/pct columns
    for nc in num_cols:
        if any(kw in nc["name"].lower() for kw in METRIC_PRIORITY_KW):
            return nc
    # 2. Prefer total/running columns
    for nc in num_cols:
        if any(kw in nc["name"].lower() for kw in TOTAL_PREFER_KW):
            return nc
    # 3. Last column (usually the most aggregated)
    return num_cols[-1] if num_cols else num_cols[0]


def detect_chart(columns: list[dict], rows: list[list]) -> dict:
    n_cols = len(columns)
    n_rows = len(rows)

    if n_cols == 0 or n_rows == 0:
        return {"type": "table"}

    # Single KPI value
    if n_cols == 1 and n_rows == 1 and _is_numeric(columns[0]):
        return {"type": "kpi", "value_col": columns[0]["name"], "label": columns[0]["name"]}

    if n_cols == 2:
        c1, c2 = columns

        # date/ordinal + number → line/bar chart
        if (_is_temporal(c1) or _is_ordinal_axis(c1)) and _is_numeric(c2):
            chart_type = "line" if _is_temporal(c1) else "bar"
            return {"type": chart_type, "x": c1["name"], "y": c2["name"], "title": c2["name"]}

        # category + number → bar chart
        if _is_categorical(c1) and _is_numeric(c2):
            return {"type": "bar", "x": c1["name"], "y": c2["name"], "title": c2["name"]}

        # number + category (reversed)
        if _is_numeric(c1) and _is_categorical(c2):
            return {"type": "bar", "x": c2["name"], "y": c1["name"], "title": c1["name"]}

        # both numeric: if first looks like ordinal axis → bar
        if _is_numeric(c1) and _is_numeric(c2) and _is_ordinal_axis(c1):
            return {"type": "bar", "x": c1["name"], "y": c2["name"], "title": c2["name"]}

    if n_cols == 3:
        date_col = next((c for c in columns if _is_temporal(c)), None)
        ordinal_col = next((c for c in columns if _is_ordinal_axis(c) and not _is_temporal(c)), None)
        num_cols = [c for c in columns if _is_numeric(c) and not _is_ordinal_axis(c)]
        cat_col = next((c for c in columns if _is_categorical(c) and not _is_temporal(c)), None)

        x_col = date_col or ordinal_col

        if x_col and num_cols:
            if cat_col:
                return {
                    "type": "line_multi",
                    "x": x_col["name"],
                    "y": num_cols[0]["name"],
                    "series": cat_col["name"],
                }
            y_col = _best_y(num_cols)
            chart_type = "line" if date_col else "bar"
            return {"type": chart_type, "x": x_col["name"], "y": y_col["name"]}

        # period/status label + value(s)
        period_col = next((c for c in columns if c["name"] in ("period", "period_label", "статус", "status", "status_order")), None)
        if period_col:
            num_col = next((c for c in columns if _is_numeric(c)), None)
            if num_col:
                return {"type": "bar", "x": period_col["name"], "y": num_col["name"]}

        # category + 1+ numerics → bar (pick best numeric)
        if cat_col and num_cols:
            return {"type": "bar", "x": cat_col["name"], "y": _best_y(num_cols)["name"]}

    # 4-6 columns: stacked bar if 1 categorical + 2+ count-type numerics (no rate/pct cols)
    if 4 <= n_cols <= 6:
        cat_col = next((c for c in columns if _is_categorical(c)), None)
        num_cols = [c for c in columns if _is_numeric(c)]
        if cat_col and len(num_cols) >= 2:
            # Check if columns look like stackable counts (no rate/pct suffix)
            count_cols = [c for c in num_cols if not any(kw in c["name"].lower() for kw in METRIC_PRIORITY_KW)]
            if len(count_cols) >= 2:
                return {
                    "type": "stacked",
                    "x": cat_col["name"],
                    "y_cols": [c["name"] for c in count_cols[:5]],
                    "title": cat_col["name"],
                }
            return {"type": "bar", "x": cat_col["name"], "y": _best_y(num_cols)["name"]}

        # date + numerics → line on best numeric
        date_col = next((c for c in columns if _is_temporal(c)), None)
        if date_col and num_cols:
            return {"type": "line", "x": date_col["name"], "y": _best_y(num_cols)["name"]}

    return {"type": "table"}


def build_chart_config(columns: list[dict], rows: list[list]) -> dict:
    return detect_chart(columns, rows)
