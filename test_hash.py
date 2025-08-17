#!/usr/bin/env python3
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# The hash from the SQL file
sql_hash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY3C2i6HGEHBp6W'

# Test various passwords
passwords = [
    'admin123',
    'admin',
    'password',
    'adminpass',
    'adminpass123',
    'admin@123',
    'Admin123',
    'Admin@123',
    'maestro',
    'maestro123'
]

print("Testing SQL hash against passwords:")
for pwd in passwords:
    try:
        if pwd_context.verify(pwd, sql_hash):
            print(f"✅ FOUND IT! The password is: '{pwd}'")
            break
    except Exception as e:
        pass
else:
    print("❌ None of the common passwords match")

# Generate a correct hash for admin123
print("\nGenerating correct hash for 'admin123':")
new_hash = pwd_context.hash('admin123')
print(f"New hash: {new_hash}")
print("\nThis hash will be different each time due to random salt, but all will work for 'admin123'")