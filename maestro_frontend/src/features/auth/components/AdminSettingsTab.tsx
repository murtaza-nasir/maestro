import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
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
  CheckCircle,
  AlertCircle,
  Search,
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
  const { t } = useTranslation();
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

  const [consistencyCheckRunning, setConsistencyCheckRunning] = useState(false);
  const [consistencyCheckResults, setConsistencyCheckResults] = useState<any>(null);
  const [showConsistencyResults, setShowConsistencyResults] = useState(false);

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
        title: t('adminSettings.error'),
        message: t('adminSettings.failedToLoadUsers')
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
        title: t('adminSettings.error'),
        message: t('adminSettings.failedToLoadSystemSettings')
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
        title: t('adminSettings.success'),
        message: t('adminSettings.userCreated')
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
        title: t('adminSettings.error'),
        message: t('adminSettings.failedToCreateUser')
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
        title: t('adminSettings.success'),
        message: t('adminSettings.userUpdated')
      });
      
      loadUsers();
    } catch (error) {
      console.error('Failed to update user:', error);
      addToast({
        type: 'error',
        title: t('adminSettings.error'),
        message: t('adminSettings.failedToUpdateUser')
      });
    }
  };

  const deleteUser = async (userId: number) => {
    if (!confirm(t('adminSettings.deleteUserConfirmation'))) {
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
        title: t('adminSettings.success'),
        message: t('adminSettings.userDeleted')
      });
      
      loadUsers();
    } catch (error) {
      console.error('Failed to delete user:', error);
      addToast({
        type: 'error',
        title: t('adminSettings.error'),
        message: t('adminSettings.failedToDeleteUser')
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

  const runConsistencyCheck = async () => {
    try {
      setConsistencyCheckRunning(true);
      const response = await apiClient.post('/api/system/consistency-check', {}, {
        headers: {
          'X-CSRF-Token': getCsrfToken()
        }
      });
      
      setConsistencyCheckResults(response.data.result);
      setShowConsistencyResults(true);
      
      addToast({
        type: 'success',
        title: t('adminSettings.consistencyCheckComplete'),
        message: t('adminSettings.foundIssues', { count: response.data.result.total_consistency_issues || 0 })
      });
    } catch (error: any) {
      console.error('Failed to run consistency check:', error);
      addToast({
        type: 'error',
        title: t('adminSettings.error'),
        message: error.response?.data?.detail || t('adminSettings.failedToRunConsistencyCheck')
      });
    } finally {
      setConsistencyCheckRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">{t('adminSettings.loading')}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            {t('adminSettings.userManagement')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex justify-between items-center mb-4">
            <p className="text-sm text-muted-foreground">
              {t('adminSettings.userManagementDescription')}
            </p>
            <Button onClick={() => setShowCreateUser(true)} className="flex items-center gap-2">
              <UserPlus className="h-4 w-4" />
              {t('adminSettings.createUser')}
            </Button>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('adminSettings.username')}</TableHead>
                <TableHead>{t('adminSettings.role')}</TableHead>
                <TableHead>{t('adminSettings.type')}</TableHead>
                <TableHead>{t('adminSettings.status')}</TableHead>
                <TableHead>{t('adminSettings.admin')}</TableHead>
                <TableHead>{t('adminSettings.actions')}</TableHead>
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
                        {user.is_active ? t('adminSettings.active') : t('adminSettings.inactive')}
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
                        {user.is_admin ? t('adminSettings.admin') : t('adminSettings.user')}
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
                        {user.is_active ? t('adminSettings.deactivate') : t('adminSettings.activate')}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggleUserAdmin(user)}
                      >
                        {user.is_admin ? t('adminSettings.removeAdmin') : t('adminSettings.makeAdmin')}
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

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            {t('adminSettings.systemConfiguration')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="registration-toggle">{t('adminSettings.enableRegistration')}</Label>
              <p className="text-sm text-muted-foreground">{t('adminSettings.enableRegistrationDescription')}</p>
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

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5" />
            {t('adminSettings.dbConsistencyCheck')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              {t('adminSettings.dbConsistencyCheckDescription')}
            </p>
            <div className="flex items-center gap-4">
              <Button
                onClick={runConsistencyCheck}
                disabled={consistencyCheckRunning}
                className="gap-2"
              >
                {consistencyCheckRunning ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('adminSettings.runningCheck')}
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" />
                    {t('adminSettings.runConsistencyCheck')}
                  </>
                )}
              </Button>
              
              {consistencyCheckResults && (
                <div className="flex items-center gap-2">
                  {consistencyCheckResults.total_consistency_issues > 0 ? (
                    <>
                      <AlertCircle className="h-4 w-4 text-yellow-500" />
                      <span className="text-sm text-yellow-600">
                        {t('adminSettings.issuesFound', { count: consistencyCheckResults.total_consistency_issues })}
                      </span>
                    </>
                  ) : (
                    <>
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      <span className="text-sm text-green-600">
                        {t('adminSettings.noIssuesFound')}
                      </span>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
          
          {consistencyCheckResults && showConsistencyResults && (
            <div className="mt-4 p-4 bg-muted rounded-lg space-y-3">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-medium">{t('adminSettings.totalUsers')}</span> {consistencyCheckResults.total_users || 0}
                </div>
                <div>
                  <span className="font-medium">{t('adminSettings.totalDocuments')}</span> {consistencyCheckResults.total_documents || 0}
                </div>
                <div>
                  <span className="font-medium">{t('adminSettings.usersChecked')}</span> {consistencyCheckResults.users_checked || 0}
                </div>
                <div>
                  <span className="font-medium">{t('adminSettings.issuesFoundLabel')}</span> {consistencyCheckResults.total_consistency_issues || 0}
                </div>
              </div>
              
              {consistencyCheckResults.users_with_issues && consistencyCheckResults.users_with_issues.length > 0 && (
                <div className="mt-3">
                  <p className="font-medium text-sm mb-2">{t('adminSettings.usersWithIssues')}</p>
                  <div className="space-y-1">
                    {consistencyCheckResults.users_with_issues.map((user: any, idx: number) => (
                      <div key={idx} className="text-sm p-2 bg-background rounded">
                        <span className="font-medium">{user.username}</span>: {t('adminSettings.userIssues', { issues_count: user.issues_count, inconsistent_documents: user.inconsistent_documents })}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {consistencyCheckResults.cleanup_performed && (
                <div className="mt-3">
                  <p className="font-medium text-sm mb-2">{t('adminSettings.cleanupPerformed')}</p>
                  <div className="text-sm">
                    <div>{t('adminSettings.documentsDeleted', { count: consistencyCheckResults.cleanup_performed.documents_deleted || 0 })}</div>
                    <div>{t('adminSettings.filesCleaned', { count: consistencyCheckResults.cleanup_performed.files_cleaned || 0 })}</div>
                  </div>
                </div>
              )}
              
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowConsistencyResults(false)}
              >
                {t('adminSettings.hideDetails')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <StorageMonitor />

      <Dialog open={showCreateUser} onOpenChange={setShowCreateUser}>
        <DialogContent className="sm:max-w-[425px] p-6">
          <DialogHeader className="pb-6">
            <DialogTitle className="text-lg font-semibold">{t('adminSettings.createNewUser')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-6 px-1">
            <div className="space-y-2">
              <Label htmlFor="new-username">{t('adminSettings.username')}</Label>
              <Input
                id="new-username"
                value={newUser.username}
                onChange={(e) => setNewUser(prev => ({ ...prev, username: e.target.value }))}
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">{t('adminSettings.password')}</Label>
              <Input
                id="new-password"
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser(prev => ({ ...prev, password: e.target.value }))}
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-role">{t('adminSettings.role')}</Label>
              <Select value={newUser.role} onValueChange={(value) => setNewUser(prev => ({ ...prev, role: value }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">{t('adminSettings.user')}</SelectItem>
                  <SelectItem value="admin">{t('adminSettings.admin')}</SelectItem>
                  <SelectItem value="readonly">{t('adminSettings.readOnly')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-user-type">{t('adminSettings.type')}</Label>
              <Select value={newUser.user_type} onValueChange={(value) => setNewUser(prev => ({ ...prev, user_type: value }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">{t('adminSettings.standard')}</SelectItem>
                  <SelectItem value="premium">{t('adminSettings.premium')}</SelectItem>
                  <SelectItem value="researcher">{t('adminSettings.researcher')}</SelectItem>
                  <SelectItem value="student">{t('adminSettings.student')}</SelectItem>
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
                {t('adminSettings.adminPrivileges')}
              </Label>
            </div>
          </div>
          <DialogFooter className="pt-4">
            <Button variant="outline" onClick={() => setShowCreateUser(false)}>
              {t('adminSettings.cancel')}
            </Button>
            <Button onClick={createUser}>
              {t('adminSettings.createUser')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showEditUser} onOpenChange={setShowEditUser}>
        <DialogContent className="sm:max-w-[425px] p-6">
          <DialogHeader className="pb-6">
            <DialogTitle className="text-lg font-semibold">
              {t('adminSettings.editUser', { username: editingUser?.username })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-6 px-1">
            <div className="space-y-2">
              <Label htmlFor="edit-username">{t('adminSettings.username')}</Label>
              <Input
                id="edit-username"
                value={editUser.username}
                onChange={(e) => setEditUser(prev => ({ ...prev, username: e.target.value }))}
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-role">{t('adminSettings.role')}</Label>
              <Select value={editUser.role} onValueChange={(value) => setEditUser(prev => ({ ...prev, role: value }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">{t('adminSettings.user')}</SelectItem>
                  <SelectItem value="admin">{t('adminSettings.admin')}</SelectItem>
                  <SelectItem value="readonly">{t('adminSettings.readOnly')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-user-type">{t('adminSettings.type')}</Label>
              <Select value={editUser.user_type} onValueChange={(value) => setEditUser(prev => ({ ...prev, user_type: value }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">{t('adminSettings.standard')}</SelectItem>
                  <SelectItem value="premium">{t('adminSettings.premium')}</SelectItem>
                  <SelectItem value="researcher">{t('adminSettings.researcher')}</SelectItem>
                  <SelectItem value="student">{t('adminSettings.student')}</SelectItem>
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
                {t('adminSettings.adminPrivileges')}
              </Label>
            </div>
          </div>
          <DialogFooter className="pt-4">
            <Button variant="outline" onClick={() => setShowEditUser(false)}>
              {t('adminSettings.cancel')}
            </Button>
            <Button onClick={saveEditUser}>
              {t('adminSettings.saveChanges')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
