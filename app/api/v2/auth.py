from fastapi import APIRouter, HTTPException, status, Response, Depends
from sqlalchemy import select
from datetime import timedelta

from app.api.deps import (
    DbSession,
    CurrentUser,
    verify_password,
    get_password_hash,
    create_access_token,
)
from app.config import settings
from app.models.user import User
from app.schemas.auth import UserCreate, UserResponse, Token, LoginRequest, AuthMeResponse

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(
    response: Response,
    login_data: LoginRequest,
    db: DbSession,
):
    """Authenticate user and return JWT token."""
    # Find user
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()

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
        secure=settings.ENVIRONMENT != "development",
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return Token(access_token=access_token, token=access_token, token_type="bearer")


@router.post("/logout")
async def logout(response: Response):
    """Logout user by clearing session cookie."""
    response.delete_cookie(key="session")
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=AuthMeResponse)
async def get_current_user_info(current_user: CurrentUser):
    """Get current authenticated user information."""
    user_response = UserResponse.from_db_user(current_user)
    return AuthMeResponse(user=user_response)


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: DbSession,
):
    """Register a new user."""
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
