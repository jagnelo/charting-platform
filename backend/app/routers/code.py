"""Unified-Python authoring APIs; execution is intentionally not hosted here."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.research import CodeAsset, CodeVersion
from app.models.user import User
from app.schemas.code import (
    CodeAssetCreate,
    CodeAssetOut,
    CodeValidationOut,
    CodeValidationRequest,
    CodeVersionCreate,
    CodeVersionOut,
)
from app.services.code_validation import validate_workstation_python

router = APIRouter(prefix="/code", tags=["code"])

_ASSET_CONTRACTS = {
    "plot": {"series"},
    "column": {"scalar"},
    "condition": {"boolean"},
    "signal": {"boolean", "events"},
    # Study Lab is intentionally the only polymorphic/artifact-producing surface.
    "study": {"scalar", "series", "boolean", "events", "table", "study"},
}


def _validate_asset_contract(kind: str, body: CodeVersionCreate, validation) -> None:
    allowed = _ASSET_CONTRACTS[kind]
    if body.output_contract not in allowed:
        raise HTTPException(
            status_code=422,
            detail={"code": "asset_output_contract_mismatch", "kind": kind, "allowed": sorted(allowed)},
        )
    if body.output_contract != "study" and validation.output_contracts != (body.output_contract,):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "declared_output_contract_mismatch",
                "declared": body.output_contract,
                "observed": list(validation.output_contracts),
            },
        )


def _asset_query():
    return select(CodeAsset).options(selectinload(CodeAsset.versions))


@router.post("/validate", response_model=CodeValidationOut)
async def validate_code(body: CodeValidationRequest, _: User = Depends(get_current_user)):
    result = validate_workstation_python(body.source)
    return CodeValidationOut(
        valid=result.valid,
        diagnostics=[item.__dict__ for item in result.diagnostics],
        dependencies=list(result.dependencies),
        lookback_hint=result.lookback_hint,
        output_contracts=list(result.output_contracts),
    )


@router.get("/assets", response_model=list[CodeAssetOut])
async def list_assets(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        _asset_query().where(CodeAsset.user_id == current_user.id).order_by(CodeAsset.name)
    )
    return result.scalars().unique().all()


@router.post("/assets", response_model=CodeAssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(
    body: CodeAssetCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    validation = validate_workstation_python(body.initial_version.source)
    if not validation.valid:
        raise HTTPException(status_code=422, detail={"code": "code_validation_failed", "diagnostics": [item.__dict__ for item in validation.diagnostics]})
    _validate_asset_contract(body.kind, body.initial_version, validation)
    asset = CodeAsset(user_id=current_user.id, stable_key=body.stable_key, name=body.name.strip(), kind=body.kind)
    asset.versions.append(_version_from_input(body.initial_version, 1, validation))
    db.add(asset)
    try:
        await db.flush()
    except Exception as exc:
        raise HTTPException(status_code=409, detail={"code": "code_asset_key_conflict"}) from exc
    return (await db.execute(_asset_query().where(CodeAsset.id == asset.id))).scalar_one()


@router.post("/assets/{asset_id}/versions", response_model=CodeVersionOut, status_code=status.HTTP_201_CREATED)
async def create_version(
    asset_id: int, body: CodeVersionCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    asset = (await db.execute(_asset_query().where(CodeAsset.id == asset_id, CodeAsset.user_id == current_user.id))).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Code asset not found")
    validation = validate_workstation_python(body.source)
    if not validation.valid:
        raise HTTPException(status_code=422, detail={"code": "code_validation_failed", "diagnostics": [item.__dict__ for item in validation.diagnostics]})
    _validate_asset_contract(asset.kind, body, validation)
    next_version = (await db.execute(select(func.max(CodeVersion.version_number)).where(CodeVersion.code_asset_id == asset.id))).scalar_one() or 0
    version = _version_from_input(body, next_version + 1, validation)
    asset.versions.append(version)
    await db.flush()
    return version


def _version_from_input(body: CodeVersionCreate, version_number: int, validation) -> CodeVersion:
    return CodeVersion(
        version_number=version_number,
        source=body.source,
        output_contract=body.output_contract,
        parameter_schema=body.parameter_schema,
        default_parameters=body.default_parameters,
        dependencies=list(validation.dependencies),
        lookback=validation.lookback_hint,
        diagnostics=[item.__dict__ for item in validation.diagnostics],
    )
