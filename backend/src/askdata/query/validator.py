from dataclasses import dataclass
import sqlglot
from sqlglot import expressions as exp
from askdata.semantic.loader import get_semantic_layer

BANNED_NODE_TYPES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
    exp.Create, exp.TruncateTable, exp.Grant, exp.Revoke, exp.Command,
)

BANNED_FUNCTIONS = {
    "pg_sleep", "pg_read_file", "pg_ls_dir", "pg_stat_file",
    "dblink", "pg_terminate_backend", "lo_import", "lo_export",
    "current_setting", "set_config",
}

# Any function sqlglot can't recognize (exp.Anonymous) is blocked by default.
# Legit PostgreSQL analytics functions (COUNT, SUM, DATE_TRUNC, EXTRACT, etc.)
# are all known to sqlglot and will never appear as Anonymous.
ALLOWED_ANONYMOUS: frozenset[str] = frozenset()

SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast", "pg_temp"}


@dataclass
class ValidationResult:
    ok: bool
    sql: str = ""
    error: str = ""
    violations: list[str] = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []


def validate_sql(sql: str, whitelist: list[str] | None = None) -> ValidationResult:
    if whitelist is None:
        sl = get_semantic_layer()
        whitelist = sl.whitelist_tables if sl else []

    whitelist_set = {t.lower() for t in whitelist}

    try:
        tree = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.errors.ParseError as e:
        return ValidationResult(ok=False, error=f"SQL parse error: {e}", violations=["parse_error"])

    violations = []

    # 1. Only SELECT at top level
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)):
        violations.append("non_select_statement")

    # 2. No banned node types anywhere
    for node in tree.walk():
        if isinstance(node, BANNED_NODE_TYPES):
            violations.append(f"banned_operation:{type(node).__name__}")

        # 3. No banned or unknown functions
        if isinstance(node, exp.Anonymous):
            fname = node.name.lower()
            if fname not in ALLOWED_ANONYMOUS:
                # Unknown function — block by default (allowlist approach)
                violations.append(f"unknown_function:{fname}")

        if isinstance(node, exp.Func) and not isinstance(node, exp.Anonymous):
            fname = node.sql_name().lower()
            if fname in BANNED_FUNCTIONS:
                violations.append(f"banned_function:{fname}")

    # 4. Whitelist tables (only if whitelist is non-empty)
    if whitelist_set:
        # Collect CTE aliases so they're not checked against the whitelist
        cte_names: set[str] = set()
        for cte in tree.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())

        for table_node in tree.find_all(exp.Table):
            tname = table_node.name.lower()
            if not tname:
                continue
            # Skip CTE references (they're not real tables)
            if tname in cte_names:
                continue
            if table_node.db and table_node.db.lower() in SYSTEM_SCHEMAS:
                violations.append(f"system_schema:{table_node.db}")
                continue
            if tname not in whitelist_set:
                violations.append(f"table_not_in_whitelist:{tname}")

    if violations:
        return ValidationResult(ok=False, error="; ".join(violations), violations=violations)

    # 5. Auto-add LIMIT if missing
    if isinstance(tree, exp.Select):
        if not tree.args.get("limit"):
            tree = tree.limit(1000)

    final_sql = tree.sql(dialect="postgres")
    return ValidationResult(ok=True, sql=final_sql)
