from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from database import crud
from database.database import get_db
from auth import security
from auth.dependencies import get_current_user_from_cookie, get_current_user_with_csrf
from api import schemas

router = APIRouter()

@router.post("/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    registration_enabled_setting = crud.get_system_setting(db, key="registration_enabled")
    if registration_enabled_setting and registration_enabled_setting.value is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User registration is disabled")

    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)

@router.post("/login")
def login_for_access_token(
    request: Request, 
    response: Response, 
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_username(db, username=form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if remember_me is requested (passed as a form field)
    remember_me = getattr(form_data, 'remember_me', False) or request.headers.get('X-Remember-Me') == 'true'
    
    # Set token expiration based on remember_me preference
    if remember_me:
        access_token_expires = timedelta(days=security.REMEMBER_ME_TOKEN_EXPIRE_DAYS)
        cookie_max_age = security.REMEMBER_ME_TOKEN_EXPIRE_DAYS * 24 * 60 * 60  # Convert to seconds
    else:
        access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
        cookie_max_age = security.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
    
    access_token = security.create_access_token(
        data={"sub": user.username, "remember_me": remember_me}, expires_delta=access_token_expires
    )
    
    # Determine if we're using HTTPS
    is_secure = request.url.scheme == "https"
    
    # Set cookie settings based on environment
    # For development (HTTP), we use less strict settings
    # For production (HTTPS), we use more secure settings
    
    # In Docker environment, we need to be more permissive with cookie settings
    # to allow cross-container communication
    cookie_settings = {
        "secure": is_secure,
        # For local development (HTTP), "lax" is more permissive and avoids
        # browser restrictions tied to "none" which requires a secure context.
        "samesite": "lax" if not is_secure else "none",
    }
    
    print(f"Setting cookies with: secure={cookie_settings['secure']}, samesite={cookie_settings['samesite']}")
    print(f"Request origin: {request.headers.get('origin', 'Unknown')}")
    print(f"Request host: {request.headers.get('host', 'Unknown')}")
    
    # Set secure HttpOnly cookie with appropriate expiration
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=cookie_max_age,
        httponly=True,
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        domain=None,  # Allow cookie to work across different ports on same host
        path="/"  # Ensure cookie is available for all paths
    )
    
    # Also store token in response body for WebSocket connections
    # This allows the frontend to extract and use it directly for WebSocket URLs
    # without relying on cookies
    
    # Generate CSRF token for double submit cookie pattern
    csrf_token = security.create_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=cookie_max_age,  # CSRF token should have same expiration as access token
        httponly=False,  # Frontend needs to read this
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        domain=None,  # Allow cookie to work across different ports on same host
        path="/"  # Ensure cookie is available for all paths
    )
    
    return {
        "message": "Login successful", 
        "csrf_token": csrf_token,
        "access_token": access_token,  # Include token in response for WebSocket use
        "token_type": "bearer",
        "expires_in": cookie_max_age,
        "remember_me": remember_me
    }

@router.post("/logout")
def logout(response: Response):
    # Clear the authentication cookies
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="csrf_token")
    return {"message": "Logout successful"}

@router.get("/me", response_model=schemas.User)
def read_users_me(current_user: schemas.User = Depends(get_current_user_from_cookie)):
    """Get current user information (protected endpoint)"""
    return current_user

@router.post("/test-csrf")
def test_csrf_protection(current_user: schemas.User = Depends(get_current_user_with_csrf)):
    """Test endpoint to verify CSRF protection is working"""
    return {"message": f"CSRF protection working for user: {current_user.username}"}

@router.post("/change-password")
def change_password(
    password_data: schemas.PasswordChange,
    current_user: schemas.User = Depends(get_current_user_with_csrf),
    db: Session = Depends(get_db)
):
    """Change user password (protected endpoint with CSRF)"""
    # Verify current password
    if not security.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Update password
    crud.update_user_password(db, user_id=current_user.id, new_password=password_data.new_password)
    
    return {"message": "Password changed successfully"}
