#!/usr/bin/env python3
"""
Setup script to create a test user for MAESTRO backend.
This script should be run after the database is initialized.
"""

import sys
import os
sys.path.append('/app')

from database.database import SessionLocal, engine
from database.models import Base, User
from auth.security import get_password_hash
from datetime import datetime

def create_first_user():
    """Create the first admin user for the application."""
    
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Check if admin user already exists
        existing_user = db.query(User).filter(User.username == "admin").first()
        if existing_user:
            print("Admin user 'admin' already exists.")
            return existing_user
        
        # Create admin user
        hashed_password = get_password_hash("adminpass123")
        admin_user = User(
            username="admin",
            hashed_password=hashed_password,
            is_admin=True,
            is_active=True,
            role="admin",
            user_type="admin",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        print(f"✅ Admin user created successfully:")
        print(f"   Username: admin")
        print(f"   Password: adminpass123")
        print(f"   User ID: {admin_user.id}")
        
        return admin_user
        
    except Exception as e:
        print(f"❌ Error creating first user: {e}")
        db.rollback()
        return None
    finally:
        db.close()

if __name__ == "__main__":
    create_first_user()
