from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from askdata.auth.deps import require_role
from askdata.auth.models import User
from askdata.semantic.loader import get_yaml_content, reload_semantic_layer, get_semantic_layer
import yaml

router = APIRouter(prefix="/admin/semantic", tags=["admin"])


class SemanticUpdateRequest(BaseModel):
    yaml: str


@router.get("")
async def get_semantic(current_user: User = Depends(require_role("admin"))):
    sl = get_semantic_layer()
    return {
        "yaml": get_yaml_content(),
        "version": sl.version,
        "metrics_count": len(sl.metrics),
        "synonyms_count": sum(len(v) for v in sl.synonyms.values()),
        "periods_count": len(sl.periods),
        "whitelist_tables": sl.whitelist_tables,
    }


@router.post("")
async def update_semantic(
    body: SemanticUpdateRequest,
    current_user: User = Depends(require_role("admin")),
):
    try:
        # Validate YAML first
        parsed = yaml.safe_load(body.yaml)
        if not isinstance(parsed, dict):
            raise ValueError("YAML must be a mapping")
        sl = reload_semantic_layer(body.yaml)
        return {
            "ok": True,
            "version": sl.version,
            "metrics_count": len(sl.metrics),
            "validation": {"ok": True},
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")


@router.get("/whitelist")
async def get_whitelist(current_user: User = Depends(require_role("admin"))):
    sl = get_semantic_layer()
    return {"tables": sl.whitelist_tables}
