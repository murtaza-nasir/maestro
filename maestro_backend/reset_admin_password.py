#!/usr/bin/env python3
"""
Reset admin password script for MAESTRO backend.
This script allows resetting the admin password to a new value.
Uses environment variables for database connection.
"""

import sys
import os
import getpass
from datetime import datetime, timezone

# Add the app directory to the path
sys.path.append('/app' if os.path.exists('/app') else os.path.dirname(os.path.abspath(__file__)))

from database.database import SessionLocal, engine
from database.models import User
from auth.security import get_password_hash
import argparse

def reset_admin_password(username='admin', new_password=None, interactive=True):
    """Reset the admin user password."""
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Find the admin user
        admin_user = db.query(User).filter(User.username == username).first()
        
        if not admin_user:
            print(f"❌ User '{username}' not found.")
            # Offer to create the user
            if interactive:
                create = input("Would you like to create an admin user? (y/n): ").lower()
                if create == 'y':
                    return create_admin_user(username, new_password, interactive)
            return False
        
        # Get new password if not provided
        if new_password is None:
            if interactive:
                while True:
                    password1 = getpass.getpass("Enter new password: ")
                    password2 = getpass.getpass("Confirm new password: ")
                    
                    if password1 != password2:
                        print("❌ Passwords do not match. Please try again.")
                        continue
                    
                    if len(password1) < 8:
                        print("❌ Password must be at least 8 characters long.")
                        continue
                    
                    new_password = password1
                    break
            else:
                # Use environment variable or generate secure password
                new_password = os.environ.get('ADMIN_PASSWORD')
                if not new_password:
                    import secrets
                    import string
                    alphabet = string.ascii_letters + string.digits + string.punctuation
                    new_password = ''.join(secrets.choice(alphabet) for _ in range(16))
                    print(f"Generated password: {new_password}")
        
        # Update password
        admin_user.hashed_password = get_password_hash(new_password)
        admin_user.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(admin_user)
        
        print(f"✅ Password reset successfully for user: {username}")
        if not interactive:
            print(f"   New password: {new_password}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error resetting password: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def create_admin_user(username='admin', password=None, interactive=True):
    """Create a new admin user."""
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Get password if not provided
        if password is None:
            if interactive:
                while True:
                    password1 = getpass.getpass("Enter password for new admin user: ")
                    password2 = getpass.getpass("Confirm password: ")
                    
                    if password1 != password2:
                        print("❌ Passwords do not match. Please try again.")
                        continue
                    
                    if len(password1) < 8:
                        print("❌ Password must be at least 8 characters long.")
                        continue
                    
                    password = password1
                    break
            else:
                # Use environment variable
                password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        
        # Get email if interactive
        email = None
        if interactive:
            email = input(f"Enter email for {username} (optional, press Enter to skip): ").strip()
        
        if not email:
            email = f"{username}@maestro.local"
        
        # Create admin user
        admin_user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            full_name="System Administrator",
            is_admin=True,
            is_active=True,
            role="admin",
            user_type="admin",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        print(f"✅ Admin user created successfully:")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print(f"   User ID: {admin_user.id}")
        if not interactive:
            print(f"   Password: {password}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def list_admin_users():
    """List all admin users in the system."""
    
    db = SessionLocal()
    
    try:
        admin_users = db.query(User).filter(User.is_admin == True).all()
        
        if not admin_users:
            print("No admin users found.")
            return
        
        print("\nAdmin Users:")
        print("-" * 60)
        for user in admin_users:
            print(f"ID: {user.id}")
            print(f"Username: {user.username}")
            print(f"Email: {user.email or 'N/A'}")
            print(f"Full Name: {user.full_name or 'N/A'}")
            print(f"Active: {user.is_active}")
            print(f"Created: {user.created_at}")
            print("-" * 60)
    
    except Exception as e:
        print(f"❌ Error listing admin users: {e}")
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description='Reset MAESTRO admin password')
    parser.add_argument('--username', '-u', default='admin', 
                       help='Username to reset (default: admin)')
    parser.add_argument('--password', '-p', 
                       help='New password (will prompt if not provided)')
    parser.add_argument('--non-interactive', '-n', action='store_true',
                       help='Run in non-interactive mode')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List all admin users')
    
    args = parser.parse_args()
    
    if args.list:
        list_admin_users()
    else:
        success = reset_admin_password(
            username=args.username,
            new_password=args.password,
            interactive=not args.non_interactive
        )
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()