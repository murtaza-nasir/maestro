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
        # Get admin credentials from environment or use defaults
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@maestro.local')
        
        # Check if admin user already exists
        existing_user = db.query(User).filter(User.username == admin_username).first()
        if existing_user:
            print(f"Admin user '{admin_username}' already exists.")
            return existing_user
        
        # Create admin user
        hashed_password = get_password_hash(admin_password)
        admin_user = User(
            username=admin_username,
            email=admin_email,
            hashed_password=hashed_password,
            full_name="System Administrator",
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
        print(f"   Username: {admin_username}")
        print(f"   Email: {admin_email}")
        print(f"   Password: {'[FROM ENVIRONMENT]' if admin_password != 'admin123' else 'admin123 (DEFAULT - CHANGE IMMEDIATELY!)'}")
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
