import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../../components/ui/card';
import { Label } from '../../../components/ui/label';
import { Input } from '../../../components/ui/input';
import { Button } from '../../../components/ui/button';
import { useToast } from '../../../components/ui/toast';
import { User, Lock } from 'lucide-react';
import { useSettingsStore } from './SettingsStore';
// import { useAuthStore } from '../store';
import { apiClient } from '../../../config/api';

export const ProfileSettingsTab: React.FC = () => {
  const { draftProfile, setProfileField } = useSettingsStore();
  // const { getCsrfToken } = useAuthStore();
  const { addToast } = useToast();
  
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: ''
  });
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  const handlePasswordChange = async () => {
    if (passwordData.new_password !== passwordData.confirm_password) {
      addToast({
        type: 'error',
        title: 'Error',
        message: 'New passwords do not match'
      });
      return;
    }

    if (passwordData.new_password.length < 6) {
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Password must be at least 6 characters long'
      });
      return;
    }

    try {
      setIsChangingPassword(true);
      await apiClient.post('/api/auth/change-password', {
        current_password: passwordData.current_password,
        new_password: passwordData.new_password
      });

      addToast({
        type: 'success',
        title: 'Success',
        message: 'Password changed successfully'
      });

      // Clear the form
      setPasswordData({
        current_password: '',
        new_password: '',
        confirm_password: ''
      });
    } catch (error: any) {
      console.error('Failed to change password:', error);
      addToast({
        type: 'error',
        title: 'Error',
        message: error.response?.data?.detail || 'Failed to change password'
      });
    } finally {
      setIsChangingPassword(false);
    }
  };

  if (!draftProfile) {
    return <div>Loading profile...</div>;
  }

  return (
    <div className="space-y-6">
      {/* User Profile Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-4 w-4" />
            User Profile
          </CardTitle>
          <CardDescription>Update your personal information.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="full_name">Full Name</Label>
            <Input
              id="full_name"
              value={draftProfile.full_name || ''}
              onChange={(e) => setProfileField('full_name', e.target.value)}
              placeholder="Enter your full name"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="location">Location</Label>
            <Input
              id="location"
              value={draftProfile.location || ''}
              onChange={(e) => setProfileField('location', e.target.value)}
              placeholder="e.g., San Francisco, CA"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="job_title">Job Title</Label>
            <Input
              id="job_title"
              value={draftProfile.job_title || ''}
              onChange={(e) => setProfileField('job_title', e.target.value)}
              placeholder="e.g., Software Engineer"
            />
          </div>
        </CardContent>
      </Card>

      {/* Password Change Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lock className="h-4 w-4" />
            Change Password
          </CardTitle>
          <CardDescription>Update your account password for security.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="current_password">Current Password</Label>
            <Input
              id="current_password"
              type="password"
              value={passwordData.current_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, current_password: e.target.value }))}
              placeholder="Enter your current password"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new_password">New Password</Label>
            <Input
              id="new_password"
              type="password"
              value={passwordData.new_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, new_password: e.target.value }))}
              placeholder="Enter your new password"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm_password">Confirm New Password</Label>
            <Input
              id="confirm_password"
              type="password"
              value={passwordData.confirm_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, confirm_password: e.target.value }))}
              placeholder="Confirm your new password"
            />
          </div>
          <Button 
            onClick={handlePasswordChange}
            disabled={isChangingPassword || !passwordData.current_password || !passwordData.new_password || !passwordData.confirm_password}
            className="w-full"
          >
            {isChangingPassword ? 'Changing Password...' : 'Change Password'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
