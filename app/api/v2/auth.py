from fastapi import APIRouter, HTTPException, status, Response, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import timedelta
from typing import Union
import logging

from app.api.deps import (
    DbSession,
    CurrentUser,
    verify_password,
    get_password_hash,
    create_access_token,
)
from app.config import settings
from app.models.user import User
from app.models.technician import Technician
from app.schemas.auth import (
    UserCreate,
    UserResponse,
    Token,
    LoginRequest,
    AuthMeResponse,
    MFASetupResponse,
    MFAVerifyRequest,
    MFALoginRequest,
    MFALoginResponse,
    MFAStatusResponse,
    BackupCodesResponse,
    MFADisableRequest,
)
from app.core.rate_limit import rate_limit_by_ip
from app.services.mfa_service import MFAManager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/login", response_model=Union[Token, MFALoginResponse])
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    db: DbSession,
):
    """Authenticate user and return JWT token (or MFA challenge if enabled)."""
    # Rate limit: 60 requests/minute per IP to prevent brute force
    rate_limit_by_ip(request, requests_per_minute=60)

    try:
        # Find user (without MFA eager loading to avoid errors if MFA tables don't exist)
        logger.info(f"Login attempt for: {login_data.email}")
        result = await db.execute(
            select(User).where(User.email == login_data.email)
        )
        user = result.scalar_one_or_none()
        logger.info(f"User found: {user is not None}")

        if not user or not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled",
            )

        # Check if MFA is enabled (gracefully handle missing MFA tables)
        mfa_enabled = False
        try:
            mfa_enabled = user.mfa_enabled
        except Exception as mfa_err:
            logger.warning(f"MFA check failed (tables may not exist): {mfa_err}")
            mfa_enabled = False

        if mfa_enabled:
            logger.info(f"MFA enabled for user {user.id}, creating MFA session")
            mfa_manager = MFAManager(db)
            session_token = await mfa_manager.create_mfa_session(user.id)
            return MFALoginResponse(
                mfa_required=True,
                session_token=session_token,
                message="MFA verification required",
            )

        # No MFA - create access token directly
        logger.info("Creating access token...")
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email},
            expires_delta=access_token_expires,
        )
        logger.info("Access token created successfully")

        # Set session cookie (HTTP-only for XSS protection)
        response.set_cookie(
            key="session",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )

        return Token(access_token=access_token, token=access_token, token_type="bearer")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Login failed: {type(e).__name__}"
        )


@router.post("/logout")
async def logout(response: Response):
    """Logout user by clearing session cookie."""
    # SECURITY: Must match the cookie settings used when setting the cookie
    response.delete_cookie(
        key="session",
        path="/",
        secure=True,
        samesite="none",
    )
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=AuthMeResponse)
async def get_current_user_info(current_user: CurrentUser, db: DbSession):
    """Get current authenticated user information.

    Checks if user has a matching Technician record (by email) to set
    the role to 'technician' and populate technician_id.
    """
    user_response = UserResponse.from_db_user(current_user)

    # Check if this user is a technician (email match)
    if not current_user.is_superuser:
        try:
            tech_result = await db.execute(
                select(Technician).where(Technician.email == current_user.email)
            )
            technician = tech_result.scalar_one_or_none()
            if technician:
                user_response.role = "technician"
                user_response.technician_id = str(technician.id)
        except Exception as e:
            logger.warning(f"Technician lookup failed for {current_user.email}: {e}")

    return AuthMeResponse(user=user_response)


@router.post("/register", response_model=UserResponse)
async def register(
    request: Request,
    user_data: UserCreate,
    db: DbSession,
):
    """Register a new user."""
    # Rate limit: 10 requests/minute per IP to prevent account enumeration
    rate_limit_by_ip(request, requests_per_minute=10)

    # Check if user exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse.from_db_user(user)


# =============================================================================
# MFA Endpoints
# =============================================================================


@router.post("/login/mfa", response_model=Token)
async def login_mfa(
    request: Request,
    response: Response,
    mfa_data: MFALoginRequest,
    db: DbSession,
):
    """Complete login with MFA verification."""
    # Rate limit: 20 requests/minute per IP
    rate_limit_by_ip(request, requests_per_minute=20)

    mfa_manager = MFAManager(db)
    success, user_id, error_message = await mfa_manager.verify_mfa_session(
        session_token=mfa_data.session_token,
        code=mfa_data.code,
        use_backup=mfa_data.use_backup_code,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_message or "MFA verification failed",
        )

    # Get user for token creation
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=access_token_expires,
    )

    # Set session cookie
    response.set_cookie(
        key="session",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    logger.info(f"MFA login successful for user {user.id}")
    return Token(access_token=access_token, token=access_token, token_type="bearer")


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: CurrentUser,
    db: DbSession,
):
    """Initialize MFA setup - generates TOTP secret and QR code."""
    mfa_manager = MFAManager(db)
    secret, qr_code = await mfa_manager.setup_mfa(current_user.id)

    logger.info(f"MFA setup initiated for user {current_user.id}")
    return MFASetupResponse(
        secret=secret,
        qr_code=qr_code,
        message="Scan the QR code with your authenticator app, then verify with a code",
    )


@router.post("/mfa/verify-setup")
async def verify_mfa_setup(
    verify_data: MFAVerifyRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Verify MFA setup with the first TOTP code from authenticator app."""
    mfa_manager = MFAManager(db)
    success = await mfa_manager.verify_setup(current_user.id, verify_data.code)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code. Please try again.",
        )

    logger.info(f"MFA setup verified for user {current_user.id}")
    return {"message": "MFA enabled successfully", "mfa_enabled": True}


@router.post("/mfa/backup-codes", response_model=BackupCodesResponse)
async def generate_backup_codes(
    current_user: CurrentUser,
    db: DbSession,
):
    """Generate new backup codes (invalidates previous codes)."""
    mfa_manager = MFAManager(db)

    try:
        codes = await mfa_manager.generate_backup_codes(current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info(f"Backup codes generated for user {current_user.id}")
    return BackupCodesResponse(
        codes=codes,
        message="Save these codes securely. Each code can only be used once. Previous codes are now invalid.",
    )


@router.get("/mfa/status", response_model=MFAStatusResponse)
async def get_mfa_status(
    current_user: CurrentUser,
    db: DbSession,
):
    """Get current MFA status for the authenticated user."""
    mfa_manager = MFAManager(db)
    status_data = await mfa_manager.get_mfa_status(current_user.id)
    return MFAStatusResponse(**status_data)


@router.post("/mfa/disable")
async def disable_mfa(
    disable_data: MFADisableRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Disable MFA (requires current TOTP code for security)."""
    mfa_manager = MFAManager(db)
    success = await mfa_manager.disable_mfa(current_user.id, disable_data.code)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code or MFA is not enabled",
        )

    logger.info(f"MFA disabled for user {current_user.id}")
    return {"message": "MFA disabled successfully", "mfa_enabled": False}
