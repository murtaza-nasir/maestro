import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../../components/ui/card';
import { Label } from '../../../components/ui/label';
import { Input } from '../../../components/ui/input';
import { Button } from '../../../components/ui/button';
import { useToast } from '../../../components/ui/toast';
import { User, Lock } from 'lucide-react';
import { useSettingsStore } from './SettingsStore';
import { apiClient } from '../../../config/api';

export const ProfileSettingsTab: React.FC = () => {
  const { t } = useTranslation();
  const { draftProfile, setProfileField } = useSettingsStore();
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
        title: t('profileSettings.error'),
        message: t('profileSettings.passwordsDoNotMatch')
      });
      return;
    }

    if (passwordData.new_password.length < 6) {
      addToast({
        type: 'error',
        title: t('profileSettings.error'),
        message: t('profileSettings.passwordTooShort')
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
        title: t('profileSettings.success'),
        message: t('profileSettings.passwordChanged')
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
        title: t('profileSettings.error'),
        message: error.response?.data?.detail || t('profileSettings.failedToChangePassword')
      });
    } finally {
      setIsChangingPassword(false);
    }
  };

  if (!draftProfile) {
    return <div>{t('profileSettings.loading')}</div>;
  }

  return (
    <div className="space-y-6">
      {/* User Profile Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-4 w-4" />
            {t('profileSettings.userProfile')}
          </CardTitle>
          <CardDescription>{t('profileSettings.userProfileDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="full_name">{t('profileSettings.fullName')}</Label>
            <Input
              id="full_name"
              value={draftProfile.full_name || ''}
              onChange={(e) => setProfileField('full_name', e.target.value)}
              placeholder={t('profileSettings.fullNamePlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="location">{t('profileSettings.location')}</Label>
            <Input
              id="location"
              value={draftProfile.location || ''}
              onChange={(e) => setProfileField('location', e.target.value)}
              placeholder={t('profileSettings.locationPlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="job_title">{t('profileSettings.jobTitle')}</Label>
            <Input
              id="job_title"
              value={draftProfile.job_title || ''}
              onChange={(e) => setProfileField('job_title', e.target.value)}
              placeholder={t('profileSettings.jobTitlePlaceholder')}
            />
          </div>
        </CardContent>
      </Card>

      {/* Password Change Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lock className="h-4 w-4" />
            {t('profileSettings.changePassword')}
          </CardTitle>
          <CardDescription>{t('profileSettings.changePasswordDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="current_password">{t('profileSettings.currentPassword')}</Label>
            <Input
              id="current_password"
              type="password"
              value={passwordData.current_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, current_password: e.target.value }))}
              placeholder={t('profileSettings.currentPasswordPlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new_password">{t('profileSettings.newPassword')}</Label>
            <Input
              id="new_password"
              type="password"
              value={passwordData.new_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, new_password: e.target.value }))}
              placeholder={t('profileSettings.newPasswordPlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm_password">{t('profileSettings.confirmNewPassword')}</Label>
            <Input
              id="confirm_password"
              type="password"
              value={passwordData.confirm_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, confirm_password: e.target.value }))}
              placeholder={t('profileSettings.confirmNewPasswordPlaceholder')}
            />
          </div>
          <Button 
            onClick={handlePasswordChange}
            disabled={isChangingPassword || !passwordData.current_password || !passwordData.new_password || !passwordData.confirm_password}
            className="w-full"
          >
            {isChangingPassword ? t('profileSettings.changingPassword') : t('profileSettings.changePassword')}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
