import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Switch } from '../../../components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../../components/ui/table';
import { Badge } from '../../../components/ui/badge';
import { useToast } from '../../../components/ui/toast';
import { StorageMonitor } from '../../../components/ui/StorageMonitor';
import { apiClient } from '../../../config/api';
import { useAuthStore } from '../store';
import { 
  Users, 
  UserPlus, 
  Settings, 
  Trash2, 
  Edit, 
  Shield, 
  ShieldCheck, 
  UserX, 
  UserCheck,
  Loader2,
} from 'lucide-react';

interface User {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  role: string;
  user_type: string;
  created_at: string;
  updated_at: string;
}

interface SystemSettings {
  registration_enabled: boolean;
  max_users_allowed: number;
  instance_name: string;
}

export const AdminSettingsTab: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [showEditUser, setShowEditUser] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [systemSettings, setSystemSettings] = useState<SystemSettings>({
    registration_enabled: true,
    max_users_allowed: 100,
    instance_name: 'MAESTRO Instance'
  });
  
  const [newUser, setNewUser] = useState({
    username: '',
    password: '',
    is_admin: false,
    role: 'user',
    user_type: 'standard'
  });

  const [editUser, setEditUser] = useState({
    username: '',
    is_admin: false,
    role: 'user',
    user_type: 'standard'
  });

  const { addToast } = useToast();
  const { getCsrfToken } = useAuthStore();

  useEffect(() => {
    loadUsers();
    loadSystemSettings();
  }, []);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/api/admin/users', {
        headers: {
          'X-CSRF-Token': getCsrfToken()
        }
      });
      setUsers(response.data);
    } catch (error) {
      console.error('Failed to load users:', error);
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to load users'
      });
    } finally {
      setLoading(false);
    }
  };

  const loadSystemSettings = async () => {
    try {
      const response = await apiClient.get('/api/admin/settings', {
        headers: {
          'X-CSRF-Token': getCsrfToken()
        }
      });
      setSystemSettings(response.data);
    } catch (error) {
      console.error('Failed to load system settings:', error);
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to load system settings'
      });
    }
  };

  const createUser = async () => {
    try {
      await apiClient.post('/api/admin/users', newUser, {
        headers: {
          'X-CSRF-Token': getCsrfToken()
        }
      });
      
      addToast({
        type: 'success',
        title: 'Success',
        message: 'User created successfully'
      });
      
      setShowCreateUser(false);
      setNewUser({
        username: '',
        password: '',
        is_admin: false,
        role: 'user',
        user_type: 'standard'
      });
      loadUsers();
    } catch (error) {
      console.error('Failed to create user:', error);
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to create user'
      });
    }
  };

  const updateUser = async (userId: number, updates: Partial<User>) => {
    try {
      await apiClient.put(`/api/admin/users/${userId}`, updates, {
        headers: {
          'X-CSRF-Token': getCsrfToken()
        }
      });
      
      addToast({
        type: 'success',
        title: 'Success',
        message: 'User updated successfully'
      });
      
      loadUsers();
    } catch (error) {
      console.error('Failed to update user:', error);
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to update user'
      });
    }
  };

  const deleteUser = async (userId: number) => {
    if (!confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      return;
    }

    try {
      await apiClient.delete(`/api/admin/users/${userId}`, {
        headers: {
          'X-CSRF-Token': getCsrfToken()
        }
      });
      
      addToast({
        type: 'success',
        title: 'Success',
        message: 'User deleted successfully'
      });
      
      loadUsers();
    } catch (error) {
      console.error('Failed to delete user:', error);
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to delete user'
      });
    }
  };

  const toggleUserStatus = async (user: User) => {
    await updateUser(user.id, { is_active: !user.is_active });
  };

  const toggleUserAdmin = async (user: User) => {
    await updateUser(user.id, { is_admin: !user.is_admin });
  };

  const openEditUser = (user: User) => {
    setEditingUser(user);
    setEditUser({
      username: user.username,
      is_admin: user.is_admin,
      role: user.role,
      user_type: user.user_type
    });
    setShowEditUser(true);
  };

  const saveEditUser = async () => {
    if (!editingUser) return;

    try {
      await updateUser(editingUser.id, editUser);
      
      setShowEditUser(false);
      setEditingUser(null);
      setEditUser({
        username: '',
        is_admin: false,
        role: 'user',
        user_type: 'standard'
      });
    } catch (error) {
      // Error handling is already done in updateUser function
    }
  };

  // const saveSystemSettings = async () => {
  //   try {
  //     await apiClient.put('/api/admin/settings', systemSettings, {
  //       headers: {
  //         'X-CSRF-Token': getCsrfToken()
  //       }
  //     });
      
  //     addToast({
  //       type: 'success',
  //       title: 'Success',
  //       message: 'System settings saved successfully'
  //     });
  //   } catch (error) {
  //     console.error('Failed to save system settings:', error);
  //     addToast({
  //       type: 'error',
  //       title: 'Error',
  //       message: 'Failed to save system settings'
  //     });
  //   }
  // };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">Loading admin settings...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* User Management Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            User Management
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-muted-foreground">
              Manage user accounts, roles, and permissions
            </p>
            <Button onClick={() => setShowCreateUser(true)} className="flex items-center gap-2">
              <UserPlus className="h-4 w-4" />
              Create User
            </Button>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Admin</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium">{user.username}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{user.role}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{user.user_type}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {user.is_active ? (
                        <UserCheck className="h-4 w-4 text-green-500" />
                      ) : (
                        <UserX className="h-4 w-4 text-red-500" />
                      )}
                      <span className={user.is_active ? 'text-green-600' : 'text-red-600'}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {user.is_admin ? (
                        <ShieldCheck className="h-4 w-4 text-blue-500" />
                      ) : (
                        <Shield className="h-4 w-4 text-muted" />
                      )}
                      <span className={user.is_admin ? 'text-blue-600' : 'text-muted-foreground'}>
                        {user.is_admin ? 'Admin' : 'User'}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggleUserStatus(user)}
                      >
                        {user.is_active ? 'Deactivate' : 'Activate'}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggleUserAdmin(user)}
                      >
                        {user.is_admin ? 'Remove Admin' : 'Make Admin'}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openEditUser(user)}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => deleteUser(user.id)}
                        className="text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* System Settings Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            System Configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="registration-toggle">Enable New User Registration</Label>
              <p className="text-sm text-muted-foreground">Allow new users to register accounts</p>
            </div>
            <Switch
              id="registration-toggle"
              checked={systemSettings.registration_enabled}
              onCheckedChange={(checked) => 
                setSystemSettings(prev => ({ ...prev, registration_enabled: checked }))
              }
            />
          </div>
        </CardContent>
      </Card>

      {/* Storage Management Section */}
      <StorageMonitor />

      {/* Create User Dialog */}
      <Dialog open={showCreateUser} onOpenChange={setShowCreateUser}>
        <DialogContent className="sm:max-w-[425px] p-6">
          <DialogHeader className="pb-6">
            <DialogTitle className="text-lg font-semibold">Create New User</DialogTitle>
          </DialogHeader>
          <div className="space-y-6 px-1">
            <div className="space-y-2">
              <Label htmlFor="new-username">Username</Label>
              <Input
                id="new-username"
                value={newUser.username}
                onChange={(e) => setNewUser(prev => ({ ...prev, username: e.target.value }))}
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">Password</Label>
              <Input
                id="new-password"
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser(prev => ({ ...prev, password: e.target.value }))}
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-role">Role</Label>
              <Select value={newUser.role} onValueChange={(value) => setNewUser(prev => ({ ...prev, role: value }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="readonly">Read Only</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-user-type">User Type</Label>
              <Select value={newUser.user_type} onValueChange={(value) => setNewUser(prev => ({ ...prev, user_type: value }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="premium">Premium</SelectItem>
                  <SelectItem value="researcher">Researcher</SelectItem>
                  <SelectItem value="student">Student</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center space-x-3 pt-2">
              <Switch
                id="new-admin"
                checked={newUser.is_admin}
                onCheckedChange={(checked) => setNewUser(prev => ({ ...prev, is_admin: checked }))}
              />
              <Label htmlFor="new-admin" className="text-sm font-medium">
                Administrator privileges
              </Label>
            </div>
          </div>
          <DialogFooter className="pt-4">
            <Button variant="outline" onClick={() => setShowCreateUser(false)}>
              Cancel
            </Button>
            <Button onClick={createUser}>
              Create User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={showEditUser} onOpenChange={setShowEditUser}>
        <DialogContent className="sm:max-w-[425px] p-6">
          <DialogHeader className="pb-6">
            <DialogTitle className="text-lg font-semibold">
              Edit User: {editingUser?.username}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-6 px-1">
            <div className="space-y-2">
              <Label htmlFor="edit-username">Username</Label>
              <Input
                id="edit-username"
                value={editUser.username}
                onChange={(e) => setEditUser(prev => ({ ...prev, username: e.target.value }))}
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-role">Role</Label>
              <Select value={editUser.role} onValueChange={(value) => setEditUser(prev => ({ ...prev, role: value }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="readonly">Read Only</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-user-type">User Type</Label>
              <Select value={editUser.user_type} onValueChange={(value) => setEditUser(prev => ({ ...prev, user_type: value }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="premium">Premium</SelectItem>
                  <SelectItem value="researcher">Researcher</SelectItem>
                  <SelectItem value="student">Student</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center space-x-3 pt-2">
              <Switch
                id="edit-admin"
                checked={editUser.is_admin}
                onCheckedChange={(checked) => setEditUser(prev => ({ ...prev, is_admin: checked }))}
              />
              <Label htmlFor="edit-admin" className="text-sm font-medium">
                Administrator privileges
              </Label>
            </div>
          </div>
          <DialogFooter className="pt-4">
            <Button variant="outline" onClick={() => setShowEditUser(false)}>
              Cancel
            </Button>
            <Button onClick={saveEditUser}>
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
