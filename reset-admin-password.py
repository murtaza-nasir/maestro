#!/usr/bin/env python3
"""
Reset admin password for MAESTRO
Run this inside the backend container to reset the admin password
"""

import sys
import os
sys.path.insert(0, '/app')

from passlib.context import CryptContext
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://maestro_user:maestro_password@postgres:5432/maestro_db")

def reset_admin_password(new_password="admin123"):
    """Reset the admin user password"""
    
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    
    try:
        with SessionLocal() as session:
            # Hash the new password
            hashed_password = pwd_context.hash(new_password)
            
            # Update admin password
            result = session.execute(
                text("UPDATE users SET hashed_password = :password WHERE username = 'admin'"),
                {"password": hashed_password}
            )
            
            if result.rowcount > 0:
                session.commit()
                print(f"✅ Admin password reset successfully!")
                print(f"   Username: admin")
                print(f"   Password: {new_password}")
                return True
            else:
                print("❌ Admin user not found!")
                
                # Try to create admin user
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
        return False

if __name__ == "__main__":
    import sys
    password = sys.argv[1] if len(sys.argv) > 1 else "admin123"
    reset_admin_password(password)