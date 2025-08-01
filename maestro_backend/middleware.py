from fastapi import Request, Depends
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional
import logging

from database.database import get_db
from database import crud
from auth import security
from ai_researcher.user_context import set_current_user

logger = logging.getLogger(__name__)

async def user_context_middleware(request: Request, call_next):
    """
    Middleware to extract user from request and set it in the user context
    for dynamic config access throughout the application.
    """
    try:
        # Extract user from JWT token (similar to get_current_user_from_cookie)
        token = request.cookies.get("access_token")
        token_source = "cookie"
        
        # If no cookie token, try Authorization header
        if not token:
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                token_source = "authorization header"
        
        if token:
            username = security.verify_token(token)
            if username:
                # Get database session
                db = next(get_db())
                try:
                    user = crud.get_user_by_username(db, username=username)
                    if user:
                        # Set user in context for dynamic config access
                        set_current_user(user)
                        logger.debug(f"Set current user context: {username}")
                finally:
                    db.close()
    except Exception as e:
        logger.debug(f"Error setting user context in middleware: {e}")
        # Don't fail the request if context setting fails
        pass
    
    # Continue with the request
    response = await call_next(request)
    return response
