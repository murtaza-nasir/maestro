from fastapi import Depends, HTTPException, WebSocket, status, Request, Header
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional

from database import crud, models
from database.database import get_db
from auth import security

security_scheme = HTTPBearer(auto_error=False)

def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)):
    """
    Extract user from JWT token stored in HttpOnly cookie or Authorization header
    """
    # First try to get token from cookie
    token = request.cookies.get("access_token")
    token_source = "cookie"
    
    # If no cookie token, try Authorization header
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            token_source = "authorization header"
    
    if not token:
        print(f"Authentication failed: No token found in cookies or Authorization header")
        print(f"  Cookies: {dict(request.cookies)}")
        print(f"  Headers: {dict(request.headers)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # print(f"Found authentication token from {token_source}, length: {len(token)}")
    
    username = security.verify_token(token)
    if username is None:
        print(f"Token verification failed for token from {token_source}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = crud.get_user_by_username(db, username=username)
    if user is None:
        print(f"User not found in database: {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # print(f"Authentication successful for user: {username} via {token_source}")
    return user

def verify_csrf_token(request: Request):
    """
    Verify CSRF token using double submit cookie pattern by reading header directly.
    """
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        x_csrf_token = request.headers.get("x-csrf-token")
        cookie_csrf_token = request.cookies.get("csrf_token")

        if not cookie_csrf_token or not x_csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing"
            )
        
        if cookie_csrf_token != x_csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token mismatch"
            )
            
    return True

def get_current_user_with_csrf(
    request: Request,
    db: Session = Depends(get_db),
    csrf_verified: bool = Depends(verify_csrf_token)
):
    """
    Get current user with CSRF protection for state-changing operations
    """
    return get_current_user_from_cookie(request, db)

def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    """
    Get current user if authenticated, otherwise return None
    """
    try:
        return get_current_user_from_cookie(request, db)
    except HTTPException:
        return None

def get_current_admin_user(current_user: models.User = Depends(get_current_user_from_cookie)):
    """
    Get current user and check if they are an admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user

async def get_current_user_from_cookie_ws(websocket: "WebSocket", db: Session):
    """
    Extract user from JWT token stored in HttpOnly cookie for WebSocket connections
    """
    try:
        # Get token from cookie
        token = websocket.cookies.get("access_token")
        
        if not token:
            return None
        
        username = security.verify_token(token)
        if username is None:
            return None
        
        user = crud.get_user_by_username(db, username=username)
        return user
    except Exception:
        return None
