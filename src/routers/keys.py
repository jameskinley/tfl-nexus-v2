from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from data.database import get_db
from data.db_models import APIKey
from security import create_api_key, require_admin_key

router = APIRouter(prefix="/keys", tags=["Keys"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class KeyMetadata(BaseModel):
    id: int
    name: str
    is_admin: bool
    is_active: bool
    request_count: int
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class CreateKeyRequest(BaseModel):
    name: str
    is_admin: bool = False


class CreateKeyResponse(BaseModel):
    key: str  # returned once only
    metadata: KeyMetadata


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[KeyMetadata], summary="List all API keys")
def list_keys(
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin_key),  # enforced at router level; explicit for clarity
) -> list[KeyMetadata]:
    records = db.query(APIKey).order_by(APIKey.id).all()
    return [KeyMetadata.model_validate(r) for r in records]


@router.post("", response_model=CreateKeyResponse, status_code=201, summary="Create an API key")
def create_key(
    body: CreateKeyRequest,
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin_key),
) -> CreateKeyResponse:
    raw, record = create_api_key(body.name, db, is_admin=body.is_admin)
    return CreateKeyResponse(key=raw, metadata=KeyMetadata.model_validate(record))


@router.delete("/{key_id}", status_code=204, summary="Revoke an API key")
def revoke_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_key: APIKey = Depends(require_admin_key),
) -> None:
    if current_key.id == key_id: #type: ignore
        raise HTTPException(status_code=400, detail="Cannot revoke your own key")
    record = db.query(APIKey).filter(APIKey.id == key_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Key not found")
    record.is_active = False #type: ignore
    db.commit()
