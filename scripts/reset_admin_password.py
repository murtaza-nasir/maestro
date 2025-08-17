#!/usr/bin/env python3
"""
Reset admin password for MAESTRO
Run this inside the backend container to reset the admin password to 'admin123'

Usage:
    docker exec -it maestro-backend python scripts/reset_admin_password.py
    
Or with a custom password:
    docker exec -it maestro-backend python scripts/reset_admin_password.py newpassword
"""

import sys
import os

# Add app to path for imports
sys.path.insert(0, '/app')

from passlib.context import CryptContext
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database connection - use environment variable or default
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://maestro_user:maestro_password@postgres:5432/maestro_db")

def reset_admin_password(new_password="admin123"):
    """Reset the admin user password"""
    
    print(f"Connecting to database...")
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    
    try:
        with SessionLocal() as session:
            # First check if admin exists
            result = session.execute(
                text("SELECT id, username, email FROM users WHERE username = 'admin'")
            )
            admin_user = result.fetchone()
            
            if admin_user:
                print(f"Found admin user: {admin_user}")
                
                # Hash the new password
                hashed_password = pwd_context.hash(new_password)
                
                # Update admin password
                result = session.execute(
                    text("UPDATE users SET hashed_password = :password WHERE username = 'admin'"),
                    {"password": hashed_password}
                )
                session.commit()
                
                print(f"✅ Admin password reset successfully!")
                print(f"   Username: admin")
                print(f"   Password: {new_password}")
                return True
            else:
                print("❌ Admin user not found!")
                print("Creating new admin user...")
                
                # Hash the new password
                hashed_password = pwd_context.hash(new_password)
                
                # Create admin user
                session.execute(
                    text("""
                        INSERT INTO users (username, email, hashed_password, full_name, is_admin, is_active, role, user_type)
                        VALUES ('admin', 'admin@maestro.local', :password, 'System Administrator', true, true, 'admin', 'admin')
                    """),
                    {"password": hashed_password}
                )
                session.commit()
                print(f"✅ Admin user created successfully!")
                print(f"   Username: admin")
                print(f"   Password: {new_password}")
                return True
                
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Get password from command line or use default
    password = sys.argv[1] if len(sys.argv) > 1 else "admin123"
    
    print(f"Resetting admin password...")
    print(f"New password will be: {password}")
    print("-" * 40)
    
    success = reset_admin_password(password)
    
    if success:
        print("-" * 40)
        print("You can now log in with:")
        print("  Username: admin")
        print(f"  Password: {password}")
    else:
        print("Failed to reset password. Please check the error above.")
        sys.exit(1)