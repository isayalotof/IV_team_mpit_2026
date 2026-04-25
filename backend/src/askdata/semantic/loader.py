import yaml
from pathlib import Path
from askdata.semantic.models import SemanticLayer, MetricDef, PeriodDef, DimensionDef

YAML_PATH = Path(__file__).parent.parent.parent.parent / "config" / "semantic_layer.yaml"

_semantic_layer: SemanticLayer | None = None


def load_semantic_layer(path: Path | None = None) -> SemanticLayer:
    global _semantic_layer
    target = path or YAML_PATH
    with open(target, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    metrics = {}
    for name, v in (raw.get("metrics") or {}).items():
        metrics[name] = MetricDef(**v)

    periods = {}
    for name, v in (raw.get("periods") or {}).items():
        if isinstance(v, str):
            periods[name] = PeriodDef(clause=v)
        else:
            periods[name] = PeriodDef(**v)

    dimensions = {}
    for name, v in (raw.get("dimensions") or {}).items():
        dimensions[name] = DimensionDef(**v)

    _semantic_layer = SemanticLayer(
        version=raw.get("version", 1),
        metrics=metrics,
        synonyms=raw.get("synonyms") or {},
        periods=periods,
        dimensions=dimensions,
        whitelist_tables=raw.get("whitelist_tables") or [],
    )
    return _semantic_layer


def get_semantic_layer() -> SemanticLayer:
    global _semantic_layer
    if _semantic_layer is None:
        try:
            _semantic_layer = load_semantic_layer()
        except FileNotFoundError:
            _semantic_layer = SemanticLayer()
    return _semantic_layer


def reload_semantic_layer(yaml_content: str) -> SemanticLayer:
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(yaml_content)
        tmp_path = Path(f.name)
    try:
        sl = load_semantic_layer(tmp_path)
        # Persist
        YAML_PATH.parent.mkdir(parents=True, exist_ok=True)
        YAML_PATH.write_text(yaml_content, encoding="utf-8")
        return sl
    finally:
        os.unlink(tmp_path)


def get_yaml_content() -> str:
    if YAML_PATH.exists():
        return YAML_PATH.read_text(encoding="utf-8")
    return ""
