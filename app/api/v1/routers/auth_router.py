from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_user, get_user_service
from app.core.rate_limit import RateLimiter
from app.core.response import created, no_content, ok
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.schemas.user import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
    UserUpdateRequest,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Auth"])

# Throttle credential-guessing / abuse on public auth endpoints (per IP, in-memory).
signup_limiter = RateLimiter(times=5, seconds=60)
login_limiter = RateLimiter(times=10, seconds=60)


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    dependencies=[Depends(signup_limiter)],
)
async def signup(
    body: UserSignupRequest,
    service: UserService = Depends(get_user_service),
):
    user = await service.register(
        email=body.email,
        username=body.username,
        full_name=body.full_name,
        password=body.password,
    )
    return created(UserResponse.model_validate(user))


@router.post(
    "/login",
    summary="Login and receive access + refresh tokens",
    dependencies=[Depends(login_limiter)],
)
async def login(
    body: UserLoginRequest,
    service: UserService = Depends(get_user_service),
):
    user = await service.authenticate(email=body.email, password=body.password)
    return ok(
        TokenResponse(
            access_token=create_access_token(subject=user.id),
            refresh_token=create_refresh_token(subject=user.id),
        )
    )


@router.post("/refresh", summary="Issue a new access token using a valid refresh token")
async def refresh_token(
    body: RefreshTokenRequest,
    service: UserService = Depends(get_user_service),
):
    payload = decode_token(body.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token."
        )
    sub: str | None = payload.get("sub")
    token_type: str | None = payload.get("type")
    if sub is None or token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token."
        )
    user = await service.get_by_id(int(sub))
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive.")
    return ok(
        TokenResponse(
            access_token=create_access_token(subject=user.id),
            refresh_token=create_refresh_token(subject=user.id),
        )
    )


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout (client-side token discard)"
)
async def logout(_: User = Depends(get_current_user)):
    return no_content()


@router.get("/profile", summary="Get the current user's profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return ok(UserResponse.model_validate(current_user))


@router.patch("/profile", summary="Update the current user's profile")
async def update_profile(
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
):
    user = await service.update_profile(
        user=current_user,
        full_name=body.full_name,
        password=body.password,
    )
    return ok(UserResponse.model_validate(user))
