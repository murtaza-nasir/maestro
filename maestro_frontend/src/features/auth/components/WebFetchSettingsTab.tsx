import React from 'react'
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from './SettingsStore'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Label } from '../../../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select'
import { FileText, Settings, Zap } from 'lucide-react'
import { Switch } from '../../../components/ui/switch'

export const WebFetchSettingsTab: React.FC = () => {
  const { t } = useTranslation()
  const { draftSettings, setDraftSettings } = useSettingsStore()

  const handleProviderChange = (provider: 'original' | 'jina' | 'original_with_jina_fallback') => {
    if (!draftSettings) return
    
    const newWebFetch = {
      ...(draftSettings.web_fetch || { provider: 'original' }),
      provider
    }
    
    setDraftSettings({ web_fetch: newWebFetch })
  }

  const handleJinaSettingChange = (field: string, value: any) => {
    if (!draftSettings) return
    
    const newWebFetch = {
      ...(draftSettings.web_fetch || { provider: 'original' }),
      [field]: value
    }
    
    setDraftSettings({ web_fetch: newWebFetch })
  }

  if (!draftSettings) {
    return <div>{t('webFetchSettings.loading')}</div>
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <FileText className="h-4 w-4" />
            {t('webFetchSettings.title')}
          </CardTitle>
          <CardDescription className="text-sm">
            {t('webFetchSettings.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-sm font-medium">{t('webFetchSettings.fetchProvider')}</Label>
              <Select
                value={draftSettings.web_fetch?.provider || 'original'}
                onValueChange={handleProviderChange}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder={t('webFetchSettings.selectFetchProvider')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="original">{t('webFetchSettings.original')}</SelectItem>
                  <SelectItem value="jina">{t('webFetchSettings.jina')}</SelectItem>
                  <SelectItem value="original_with_jina_fallback">{t('webFetchSettings.originalWithJinaFallback')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {(draftSettings.web_fetch?.provider || 'original') === 'original' && (
              <div className="space-y-3 pl-3 border-l-2 border-gray-200 bg-gray-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  {t('webFetchSettings.originalDescription')}
                </p>
                <ul className="text-xs text-muted-foreground space-y-1">
                  <li>• {t('webFetchSettings.originalFeature1')}</li>
                  <li>• {t('webFetchSettings.originalFeature2')}</li>
                  <li>• {t('webFetchSettings.originalFeature3')}</li>
                  <li>• {t('webFetchSettings.originalFeature4')}</li>
                </ul>
              </div>
            )}

            {draftSettings.web_fetch?.provider === 'jina' && (
              <div className="space-y-3 pl-3 border-l-2 border-orange-200 bg-orange-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  {t('webFetchSettings.jinaDescription')}
                </p>
                <p className="text-xs text-muted-foreground mb-3">
                  {t('webFetchSettings.jinaApiKeyNote')}
                </p>
              </div>
            )}
            
            {draftSettings.web_fetch?.provider === 'original_with_jina_fallback' && (
              <div className="space-y-3 pl-3 border-l-2 border-blue-200 bg-blue-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  {t('webFetchSettings.fallbackDescription')}
                </p>
                <ul className="text-xs text-muted-foreground space-y-1">
                  <li>• {t('webFetchSettings.fallbackFeature1')}</li>
                  <li>• {t('webFetchSettings.fallbackFeature2')}</li>
                  <li>• {t('webFetchSettings.fallbackFeature3')}</li>
                  <li>• {t('webFetchSettings.fallbackFeature4')}</li>
                </ul>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Jina-specific configuration */}
      {(draftSettings.web_fetch?.provider === 'jina' || draftSettings.web_fetch?.provider === 'original_with_jina_fallback') && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Settings className="h-4 w-4" />
              {t('webFetchSettings.jinaConfiguration')}
            </CardTitle>
            <CardDescription className="text-sm">
              {t('webFetchSettings.jinaConfigurationDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="browser-engine" className="text-sm">{t('webFetchSettings.browserEngine')}</Label>
                <Select
                  value={draftSettings.web_fetch?.jina_browser_engine || 'default'}
                  onValueChange={(value) => handleJinaSettingChange('jina_browser_engine', value)}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder={t('webFetchSettings.selectBrowserEngine')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">{t('webFetchSettings.defaultBalanced')}</SelectItem>
                    <SelectItem value="chrome">{t('webFetchSettings.chromeHighQuality')}</SelectItem>
                    <SelectItem value="lightweight">{t('webFetchSettings.lightweightFast')}</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {t('webFetchSettings.browserEngineDescription')}
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="content-format" className="text-sm">{t('webFetchSettings.contentFormat')}</Label>
                <Select
                  value={draftSettings.web_fetch?.jina_content_format || 'default'}
                  onValueChange={(value) => handleJinaSettingChange('jina_content_format', value)}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder={t('webFetchSettings.selectContentFormat')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">{t('webFetchSettings.defaultMarkdown')}</SelectItem>
                    <SelectItem value="json">{t('webFetchSettings.jsonStructured')}</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {t('webFetchSettings.contentFormatDescription')}
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="timeout" className="text-sm">{t('webFetchSettings.timeout')}</Label>
                <Input
                  id="timeout"
                  type="number"
                  min="5"
                  max="60"
                  value={draftSettings.web_fetch?.jina_timeout || 10}
                  onChange={(e) => {
                    const value = Math.max(5, Math.min(60, parseInt(e.target.value) || 10))
                    handleJinaSettingChange('jina_timeout', value)
                  }}
                  className="h-8 text-sm"
                />
                <p className="text-xs text-muted-foreground">
                  {t('webFetchSettings.timeoutDescription')}
                </p>
              </div>

              <div className="space-y-3 pt-2">
                <Label className="text-sm">{t('webFetchSettings.contentProcessingOptions')}</Label>
                
                <div className="flex items-center space-x-2">
                  <Switch
                    id="gather-links"
                    checked={draftSettings.web_fetch?.jina_gather_links || false}
                    onCheckedChange={(checked) => handleJinaSettingChange('jina_gather_links', checked)}
                  />
                  <Label htmlFor="gather-links" className="text-sm font-normal cursor-pointer">
                    {t('webFetchSettings.gatherLinks')}
                  </Label>
                </div>

                <div className="flex items-center space-x-2">
                  <Switch
                    id="gather-images"
                    checked={draftSettings.web_fetch?.jina_gather_images || false}
                    onCheckedChange={(checked) => handleJinaSettingChange('jina_gather_images', checked)}
                  />
                  <Label htmlFor="gather-images" className="text-sm font-normal cursor-pointer">
                    {t('webFetchSettings.gatherImages')}
                  </Label>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Performance comparison */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Zap className="h-4 w-4" />
            {t('webFetchSettings.comparisonTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-3 gap-2">
              <div className="font-medium">{t('webFetchSettings.feature')}</div>
              <div className="font-medium">{t('webFetchSettings.builtIn')}</div>
              <div className="font-medium">{t('webFetchSettings.jinaReader')}</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>{t('webFetchSettings.jsRendering')}</div>
              <div className="text-muted-foreground">{t('webFetchSettings.limited')}</div>
              <div className="text-green-600">{t('webFetchSettings.fullBrowser')}</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>{t('webFetchSettings.pdfSupport')}</div>
              <div className="text-green-600">{t('webFetchSettings.native')}</div>
              <div className="text-green-600">{t('webFetchSettings.supported')}</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>{t('webFetchSettings.caching')}</div>
              <div className="text-green-600">{t('webFetchSettings.localCache')}</div>
              <div className="text-muted-foreground">{t('webFetchSettings.noCache')}</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>{t('webFetchSettings.apiCost')}</div>
              <div className="text-green-600">{t('webFetchSettings.free')}</div>
              <div className="text-orange-600">{t('webFetchSettings.rateLimitedPaid')}</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>{t('webFetchSettings.contentQuality')}</div>
              <div className="text-muted-foreground">{t('webFetchSettings.good')}</div>
              <div className="text-green-600">{t('webFetchSettings.excellent')}</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}