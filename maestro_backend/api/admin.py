from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import crud, models
from database.database import get_db
from api import schemas
from auth.dependencies import get_current_admin_user

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin_user)],
    responses={404: {"description": "Not found"}},
)

@router.get("/users", response_model=List[schemas.User])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve all users. Admin only.
    """
    users = crud.get_users(db, skip=skip, limit=limit)
    return users

@router.post("/users", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user. Admin only.
    """
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)

@router.put("/users/{user_id}", response_model=schemas.User)
def update_user_details(user_id: str, user_update: schemas.UserUpdate, db: Session = Depends(get_db)):
    """
    Update a user's details (e.g., role, user_type). Admin only.
    """
    db_user = crud.get_user(db, user_id=user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.update_user(db=db, user_id=user_id, user_update=user_update)

@router.delete("/users/{user_id}", response_model=schemas.User)
def delete_user(user_id: str, db: Session = Depends(get_db)):
    """
    Delete a user. Admin only.
    """
    db_user = crud.get_user(db, user_id=user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.delete_user(db=db, user_id=user_id)

@router.get("/settings", response_model=schemas.SystemSettingsResponse)
def get_system_settings(db: Session = Depends(get_db)):
    """
    Get system-wide settings. Admin only.
    """
    registration_enabled_setting = crud.get_system_setting(db, key="registration_enabled")
    max_users_allowed_setting = crud.get_system_setting(db, key="max_users_allowed")
    instance_name_setting = crud.get_system_setting(db, key="instance_name")

    return schemas.SystemSettingsResponse(
        registration_enabled=registration_enabled_setting.value if registration_enabled_setting else True,
        max_users_allowed=max_users_allowed_setting.value if max_users_allowed_setting else 100,
        instance_name=instance_name_setting.value if instance_name_setting else "MAESTRO Instance"
    )

@router.put("/settings", response_model=schemas.SystemSettingsResponse)
def update_system_settings(settings_update: schemas.SystemSettingsUpdate, db: Session = Depends(get_db)):
    """
    Update system-wide settings. Admin only.
    """
    if settings_update.registration_enabled is not None:
        crud.update_system_setting(db, key="registration_enabled", value=settings_update.registration_enabled)
    if settings_update.max_users_allowed is not None:
        crud.update_system_setting(db, key="max_users_allowed", value=settings_update.max_users_allowed)
    if settings_update.instance_name is not None:
        crud.update_system_setting(db, key="instance_name", value=settings_update.instance_name)

    return get_system_settings(db)
