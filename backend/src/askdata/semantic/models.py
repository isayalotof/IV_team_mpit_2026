from pydantic import BaseModel
from typing import Any


class MetricDef(BaseModel):
    description: str
    sql_expr: str
    base_table: str
    filters: str = ""
    format: str = "integer"


class PeriodDef(BaseModel):
    start: str = ""
    end: str = ""
    clause: str = ""


class DimensionDef(BaseModel):
    column: str
    tables: list[str] = []
    join: str = ""
    display_column: str = ""


class SemanticLayer(BaseModel):
    version: int = 1
    metrics: dict[str, MetricDef] = {}
    synonyms: dict[str, list[str]] = {}
    periods: dict[str, PeriodDef | str] = {}
    dimensions: dict[str, DimensionDef] = {}
    whitelist_tables: list[str] = []
