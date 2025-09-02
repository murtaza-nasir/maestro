# Admin Settings

Administrator-only controls for managing users, system configuration, and database maintenance.

**Note:** This tab is only visible to users with administrator privileges.

## User Management

Manage user accounts, roles, and permissions through the user management table.

### User Table

The table displays all registered users with the following information:

- **Username** - User login identifier
- **Role** - User role (user, admin, readonly)
- **Type** - Account type (standard, premium, researcher, student)
- **Status** - Active or inactive (shown with icon)
- **Admin** - Administrator privileges (shown with shield icon)
- **Actions** - Management controls

### Creating New Users

1. Click the **"Create User"** button
2. Fill in the required fields:
      - **Username** - Unique login name
      - **Password** - User's password
      - **Role** - Select from: User, Admin, Read Only
      - **User Type** - Select from: Standard, Premium, Researcher, Student
      - **Administrator privileges** - Toggle switch for admin rights
3. Click **"Create User"** to save

### Managing Existing Users

**Quick Actions per User:**

- **Activate/Deactivate** - Toggle user's ability to log in
- **Make Admin/Remove Admin** - Grant or revoke administrator privileges
- **Edit** - Modify username, role, or user type
- **Delete** - Permanently remove user (requires confirmation)

**Edit User Dialog:**
- Change username
- Modify role
- Update user type
- Toggle admin privileges

## System Configuration

### Registration Settings

**Enable New User Registration**

- Toggle switch to allow or prevent new user self-registration
- When disabled, only administrators can create new accounts

## Database Consistency Check

Tool for checking document storage consistency across the database, vector store, and file system.

### Running a Check

1. Click **"Run Consistency Check"** button
2. Wait for the analysis to complete
3. Review the results displayed

### Check Results

The consistency check reports:

- **Total Users** - Number of users in the system
- **Total Documents** - Total document count
- **Users Checked** - Number of users analyzed
- **Issues Found** - Total inconsistencies detected

If issues are found, details include:

- Users with issues and their document counts
- Cleanup performed (if any)
- Documents deleted and files cleaned

## Storage Monitor

The Storage Monitor component displays system storage usage and statistics. This helps administrators track disk usage and identify storage issues.

## Important Notes

- At least one admin account must remain in the system
- Deleting a user permanently removes all their data
- Deactivated users cannot log in but their data is preserved
- Changes to user status and privileges take effect immediately

## Best Practices

- Regularly review user accounts and permissions
- Deactivate rather than delete users when possible
- Run consistency checks periodically
- Monitor storage usage to prevent disk space issues
- Keep the admin password secure and change it from defaults

## Next Steps

- [Profile Settings](profile.md) - Manage your personal account
- [AI Configuration](ai-config.md) - Configure language models
- [Research Settings](research-config.md) - Set research parameters