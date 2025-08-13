import React, { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../components/ui/dialog'
import { Button } from '../../../components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs'
import { useSettingsStore } from './SettingsStore'
import { useAuthStore } from '../store'
import { AISettingsTab } from './AISettingsTab'
import { SearchSettingsTab } from './SearchSettingsTab'
import { ResearchSettingsTab } from './ResearchSettingsTab'
import { ProfileSettingsTab } from './ProfileSettingsTab'
import { AppearanceSettingsTab } from './AppearanceSettingsTab'
import { AdminSettingsTab } from './AdminSettingsTab'
import { Card, CardContent } from '../../../components/ui/card'
import { AlertCircle, Loader2, User, Cpu, Search, Beaker, Paintbrush, Shield } from 'lucide-react'

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export const SettingsDialog: React.FC<SettingsDialogProps> = ({ open, onOpenChange }) => {
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

  // const handleClose = () => {
  //   discardDraftChanges()
  //   onOpenChange(false)
  // }

  if (isLoading && !settings) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-visible">
          <div className="flex items-center justify-center p-8">
            <Loader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2">Loading settings...</span>
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[85vh] flex flex-col overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 flex-shrink-0 border-b border-border">
          <DialogTitle className="text-foreground">Settings</DialogTitle>
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
            <TabsList className={`grid w-full ${user?.is_admin ? 'grid-cols-6' : 'grid-cols-5'} h-10 flex-shrink-0 mb-4`}>
              <TabsTrigger value="profile" className="text-sm">
                <User className="w-4 h-4 mr-2" />
                Profile
              </TabsTrigger>
              <TabsTrigger value="appearance" className="text-sm">
                <Paintbrush className="w-4 h-4 mr-2" />
                Appearance
              </TabsTrigger>
              <TabsTrigger value="ai" className="text-sm">
                <Cpu className="w-4 h-4 mr-2" />
                AI Config
              </TabsTrigger>
              <TabsTrigger value="search" className="text-sm">
                <Search className="w-4 h-4 mr-2" />
                Search
              </TabsTrigger>
              <TabsTrigger value="research" className="text-sm">
                <Beaker className="w-4 h-4 mr-2" />
                Research
              </TabsTrigger>
              {user?.is_admin && (
                <TabsTrigger value="admin" className="text-sm">
                  <Shield className="w-4 h-4 mr-2" />
                  Admin
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
                Saving...
              </>
            ) : (
              'Save & Close'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
