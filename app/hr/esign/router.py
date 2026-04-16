from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.hr.esign.schemas import (
    SignatureRequestCreateIn,
    SignatureRequestOut,
    SubmitSignatureIn,
)
from app.hr.esign.services import (
    SignatureError,
    create_signature_request,
    mark_viewed,
    submit_signature,
)


# Admin-side router (auth required). Mounted under hr_router at /hr/sign.
esign_admin_router = APIRouter(prefix="/sign", tags=["hr-esign-admin"])


@esign_admin_router.post(
    "/requests",
    response_model=SignatureRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_request(
    payload: SignatureRequestCreateIn, db: DbSession, user: CurrentUser
) -> SignatureRequestOut:
    try:
        req = await create_signature_request(db, payload, actor_user_id=user.id)
    except SignatureError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return SignatureRequestOut.model_validate(req)


# Public router (no auth).  Mounted separately in main.py at /api/v2/public.
esign_public_router = APIRouter(prefix="/sign", tags=["hr-esign-public"])


@esign_public_router.get("/{token}", response_model=SignatureRequestOut)
async def view_request(
    token: str, db: DbSession, request: Request
) -> SignatureRequestOut:
    try:
        req = await mark_viewed(
            db,
            token=token,
            ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
        )
    except SignatureError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return SignatureRequestOut.model_validate(req)


@esign_public_router.post("/{token}/submit")
async def submit(
    token: str,
    payload: SubmitSignatureIn,
    db: DbSession,
    request: Request,
) -> dict:
    try:
        signed = await submit_signature(
            db,
            token=token,
            signature_image_base64=payload.signature_image_base64,
            consent_confirmed=payload.consent_confirmed,
            ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
        )
    except SignatureError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"signed_document_id": str(signed.id)}
