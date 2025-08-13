import React, { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../components/ui/dialog'
import { Button } from '../../../components/ui/button'
import { Label } from '../../../components/ui/label'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Switch } from '../../../components/ui/switch'
import { Settings, RotateCcw, Info } from 'lucide-react'
import { useSettingsStore } from '../../auth/components/SettingsStore'

interface WritingSearchSettings {
  useWebSearch: boolean
  deepSearch: boolean
  maxIterations: number
  maxQueries: number
  deepSearchIterations: number
  deepSearchQueries: number
}

interface WritingSearchSettingsModalProps {
  isOpen: boolean
  onClose: () => void
  settings: WritingSearchSettings
  onSave: (settings: WritingSearchSettings) => void
}

export const WritingSearchSettingsModal: React.FC<WritingSearchSettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSave,
}) => {
  const { settings: userSettings } = useSettingsStore()
  const [localSettings, setLocalSettings] = useState<WritingSearchSettings>(settings)

  // Get defaults from user settings or use hardcoded defaults
  const getDefaults = (): WritingSearchSettings => {
    const params = userSettings?.research_parameters
    return {
      useWebSearch: true,
      deepSearch: false,
      maxIterations: params?.writing_search_max_iterations ?? 1,
      maxQueries: params?.writing_search_max_queries ?? 3,
      deepSearchIterations: params?.writing_deep_search_iterations ?? 3,
      deepSearchQueries: params?.writing_deep_search_queries ?? 10,
    }
  }

  useEffect(() => {
    setLocalSettings(settings)
  }, [settings])

  const handleSave = () => {
    onSave(localSettings)
    onClose()
  }

  const handleReset = () => {
    const defaults = getDefaults()
    setLocalSettings({
      ...localSettings,
      maxIterations: defaults.maxIterations,
      maxQueries: defaults.maxQueries,
      deepSearchIterations: defaults.deepSearchIterations,
      deepSearchQueries: defaults.deepSearchQueries,
    })
  }

  const handleCancel = () => {
    setLocalSettings(settings) // Reset to original settings
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleCancel()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Writing Search Settings
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Basic Settings */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Basic Settings</CardTitle>
              <CardDescription className="text-xs">Configure search behavior for this chat</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="web-search" className="text-sm">Enable Web Search</Label>
                  <div className="text-xs text-muted-foreground">Search the web for additional information</div>
                </div>
                <Switch
                  id="web-search"
                  checked={localSettings.useWebSearch}
                  onCheckedChange={(checked) => setLocalSettings({ ...localSettings, useWebSearch: checked })}
                />
              </div>

              {localSettings.useWebSearch && (
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="deep-search" className="text-sm">Deep Search Mode</Label>
                    <div className="text-xs text-muted-foreground">
                      Use multiple iterations with quality assessment
                    </div>
                  </div>
                  <Switch
                    id="deep-search"
                    checked={localSettings.deepSearch}
                    onCheckedChange={(checked) => setLocalSettings({ ...localSettings, deepSearch: checked })}
                  />
                </div>
              )}
            </CardContent>
          </Card>

          {/* Regular Search Settings */}
          {localSettings.useWebSearch && !localSettings.deepSearch && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">Regular Search Settings</CardTitle>
                <CardDescription className="text-xs">Configure parameters for regular search</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="max-iterations" className="text-sm">
                    Maximum Iterations
                    <span className="ml-2 text-xs text-muted-foreground">(1-5)</span>
                  </Label>
                  <Input
                    id="max-iterations"
                    type="number"
                    min={1}
                    max={5}
                    value={localSettings.maxIterations}
                    onChange={(e) => setLocalSettings({ ...localSettings, maxIterations: parseInt(e.target.value) || 1 })}
                    className="h-8"
                  />
                  <div className="flex items-start gap-1">
                    <Info className="h-3 w-3 text-muted-foreground mt-0.5" />
                    <p className="text-xs text-muted-foreground">
                      Number of quality refinement attempts per search
                    </p>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="max-queries" className="text-sm">
                    Maximum Decomposed Queries
                    <span className="ml-2 text-xs text-muted-foreground">(1-10)</span>
                  </Label>
                  <Input
                    id="max-queries"
                    type="number"
                    min={1}
                    max={10}
                    value={localSettings.maxQueries}
                    onChange={(e) => setLocalSettings({ ...localSettings, maxQueries: parseInt(e.target.value) || 3 })}
                    className="h-8"
                  />
                  <div className="flex items-start gap-1">
                    <Info className="h-3 w-3 text-muted-foreground mt-0.5" />
                    <p className="text-xs text-muted-foreground">
                      Maximum number of focused searches to perform
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Deep Search Settings */}
          {localSettings.useWebSearch && localSettings.deepSearch && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">Deep Search Settings</CardTitle>
                <CardDescription className="text-xs">Configure parameters for deep search</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="deep-iterations" className="text-sm">
                    Maximum Iterations
                    <span className="ml-2 text-xs text-muted-foreground">(1-10)</span>
                  </Label>
                  <Input
                    id="deep-iterations"
                    type="number"
                    min={1}
                    max={10}
                    value={localSettings.deepSearchIterations}
                    onChange={(e) => setLocalSettings({ ...localSettings, deepSearchIterations: parseInt(e.target.value) || 3 })}
                    className="h-8"
                  />
                  <div className="flex items-start gap-1">
                    <Info className="h-3 w-3 text-muted-foreground mt-0.5" />
                    <p className="text-xs text-muted-foreground">
                      Number of quality refinement attempts per search
                    </p>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="deep-queries" className="text-sm">
                    Maximum Decomposed Queries
                    <span className="ml-2 text-xs text-muted-foreground">(1-20)</span>
                  </Label>
                  <Input
                    id="deep-queries"
                    type="number"
                    min={1}
                    max={20}
                    value={localSettings.deepSearchQueries}
                    onChange={(e) => setLocalSettings({ ...localSettings, deepSearchQueries: parseInt(e.target.value) || 10 })}
                    className="h-8"
                  />
                  <div className="flex items-start gap-1">
                    <Info className="h-3 w-3 text-muted-foreground mt-0.5" />
                    <p className="text-xs text-muted-foreground">
                      Maximum number of focused searches to perform
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <DialogFooter className="flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            className="mr-auto"
          >
            <RotateCcw className="h-4 w-4 mr-1" />
            Reset to Defaults
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleCancel}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave}>
              Save Settings
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}