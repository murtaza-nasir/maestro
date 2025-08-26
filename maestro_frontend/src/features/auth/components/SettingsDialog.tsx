import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../components/ui/dialog'
import { Button } from '../../../components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs'
import { useSettingsStore } from './SettingsStore'
import { useAuthStore } from '../store'
import { AISettingsTab } from './AISettingsTab'
import { SearchSettingsTab } from './SearchSettingsTab'
import { WebFetchSettingsTab } from './WebFetchSettingsTab'
import { ResearchSettingsTab } from './ResearchSettingsTab'
import { ProfileSettingsTab } from './ProfileSettingsTab'
import { AppearanceSettingsTab } from './AppearanceSettingsTab'
import { AdminSettingsTab } from './AdminSettingsTab'
import { Card, CardContent } from '../../../components/ui/card'
import { AlertCircle, Loader2, User, Cpu, Search, Beaker, Paintbrush, Shield, FileText } from 'lucide-react'

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export const SettingsDialog: React.FC<SettingsDialogProps> = ({ open, onOpenChange }) => {
  const { t } = useTranslation()
  const { settings, profile, isLoading, error, loadSettings, updateSettings } = useSettingsStore()
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState('profile')

  useEffect(() => {
    if (open && (!settings || !profile)) {
      loadSettings()
    }
  }, [open, settings, profile, loadSettings])

  const handleSave = async () => {
    await updateSettings()
    onOpenChange(false)
  }

  if (isLoading && !settings) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-visible">
          <div className="flex items-center justify-center p-8">
            <Loader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2">{t('settingsDialog.loading')}</span>
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[85vh] flex flex-col overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 flex-shrink-0 border-b border-border">
          <DialogTitle className="text-foreground">{t('settingsDialog.title')}</DialogTitle>
        </DialogHeader>

        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {error && (
            <div className="px-6 pt-4">
              <Card className="bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
                <CardContent className="p-4">
                  <div className="flex items-center">
                    <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
                    <span className="text-red-700 dark:text-red-300">{error}</span>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full flex-1 flex flex-col min-h-0 px-6 pt-4">
            <TabsList className={`grid w-full ${user?.is_admin ? 'grid-cols-7' : 'grid-cols-6'} h-10 flex-shrink-0 mb-4`}>
              <TabsTrigger value="profile" className="text-sm">
                <User className="w-4 h-4 mr-2" />
                {t('settingsDialog.tabs.profile')}
              </TabsTrigger>
              <TabsTrigger value="appearance" className="text-sm">
                <Paintbrush className="w-4 h-4 mr-2" />
                {t('settingsDialog.tabs.appearance')}
              </TabsTrigger>
              <TabsTrigger value="ai" className="text-sm">
                <Cpu className="w-4 h-4 mr-2" />
                {t('settingsDialog.tabs.aiConfig')}
              </TabsTrigger>
              <TabsTrigger value="search" className="text-sm">
                <Search className="w-4 h-4 mr-2" />
                {t('settingsDialog.tabs.search')}
              </TabsTrigger>
              <TabsTrigger value="web-fetch" className="text-sm">
                <FileText className="w-4 h-4 mr-2" />
                {t('settingsDialog.tabs.webFetch')}
              </TabsTrigger>
              <TabsTrigger value="research" className="text-sm">
                <Beaker className="w-4 h-4 mr-2" />
                {t('settingsDialog.tabs.research')}
              </TabsTrigger>
              {user?.is_admin && (
                <TabsTrigger value="admin" className="text-sm">
                  <Shield className="w-4 h-4 mr-2" />
                  {t('settingsDialog.tabs.admin')}
                </TabsTrigger>
              )}
            </TabsList>

            <div className="flex-1 min-h-0 overflow-hidden rounded-b-lg">
              <TabsContent value="profile" className="h-full overflow-y-auto settings-scrollbar data-[state=active]:flex data-[state=active]:flex-col pr-2 pb-4">
                <ProfileSettingsTab />
              </TabsContent>

              <TabsContent value="appearance" className="h-full overflow-y-auto settings-scrollbar data-[state=active]:flex data-[state=active]:flex-col pr-2 pb-4">
                <AppearanceSettingsTab />
              </TabsContent>

              <TabsContent value="ai" className="h-full overflow-y-auto settings-scrollbar data-[state=active]:flex data-[state=active]:flex-col pr-2 pb-4">
                <AISettingsTab />
              </TabsContent>

              <TabsContent value="search" className="h-full overflow-y-auto settings-scrollbar data-[state=active]:flex data-[state=active]:flex-col pr-2 pb-4">
                <SearchSettingsTab />
              </TabsContent>

              <TabsContent value="web-fetch" className="h-full overflow-y-auto settings-scrollbar data-[state=active]:flex data-[state=active]:flex-col pr-2 pb-4">
                <WebFetchSettingsTab />
              </TabsContent>

              <TabsContent value="research" className="h-full overflow-y-auto settings-scrollbar data-[state=active]:flex data-[state=active]:flex-col pr-2 pb-4">
                <ResearchSettingsTab />
              </TabsContent>
              {user?.is_admin && (
                <TabsContent value="admin" className="h-full overflow-y-auto settings-scrollbar data-[state=active]:flex data-[state=active]:flex-col pr-2 pb-4">
                  <AdminSettingsTab />
                </TabsContent>
              )}
            </div>
          </Tabs>
        </div>

        <DialogFooter className="px-6 pt-4 pb-6 flex-shrink-0 flex items-center justify-end border-t bg-background/95 backdrop-blur-sm mt-4">
          <Button onClick={handleSave} disabled={isLoading} className="min-w-[120px]">
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                {t('settingsDialog.saving')}
              </>
            ) : (
              t('settingsDialog.saveAndClose')
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
