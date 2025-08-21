import React from 'react'
import { useSettingsStore } from './SettingsStore'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Label } from '../../../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select'
import { FileText, Settings, Zap } from 'lucide-react'
import { Switch } from '../../../components/ui/switch'

export const WebFetchSettingsTab: React.FC = () => {
  const { draftSettings, setDraftSettings } = useSettingsStore()

  const handleProviderChange = (provider: 'original' | 'jina') => {
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
    return <div>Loading...</div>
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Web Page Fetching Configuration
          </CardTitle>
          <CardDescription className="text-sm">
            Configure how web pages are fetched and processed for research.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-sm font-medium">Fetch Provider</Label>
              <Select
                value={draftSettings.web_fetch?.provider || 'original'}
                onValueChange={handleProviderChange}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Select fetch provider" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="original">Original (Built-in)</SelectItem>
                  <SelectItem value="jina">Jina Reader API</SelectItem>
                  <SelectItem value="original_with_jina_fallback">Original + Jina Fallback</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {(draftSettings.web_fetch?.provider || 'original') === 'original' && (
              <div className="space-y-3 pl-3 border-l-2 border-gray-200 bg-gray-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  Built-in web page fetcher using newspaper3k and PyMuPDF for content extraction.
                </p>
                <ul className="text-xs text-muted-foreground space-y-1">
                  <li>• Supports HTML and PDF content</li>
                  <li>• Local caching for improved performance</li>
                  <li>• Automatic metadata extraction</li>
                  <li>• No API key required</li>
                </ul>
              </div>
            )}

            {draftSettings.web_fetch?.provider === 'jina' && (
              <div className="space-y-3 pl-3 border-l-2 border-orange-200 bg-orange-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  Jina Reader API (r.jina.ai) provides advanced web page reading with browser rendering.
                </p>
                <p className="text-xs text-muted-foreground mb-3">
                  Uses the same API key configured in Search settings. Free tier available with rate limits.
                </p>
              </div>
            )}
            
            {draftSettings.web_fetch?.provider === 'original_with_jina_fallback' && (
              <div className="space-y-3 pl-3 border-l-2 border-blue-200 bg-blue-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  Uses the built-in fetcher first, automatically falling back to Jina Reader API if the site blocks access.
                </p>
                <ul className="text-xs text-muted-foreground space-y-1">
                  <li>• Best of both worlds - fast local fetching when possible</li>
                  <li>• Automatic fallback for sites that block scrapers (403 errors)</li>
                  <li>• Uses Jina settings configured below when fallback is triggered</li>
                  <li>• Requires Jina API key for fallback functionality</li>
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
              Jina Reader Configuration
            </CardTitle>
            <CardDescription className="text-sm">
              Configure advanced options for Jina Reader API.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="browser-engine" className="text-sm">Browser Engine</Label>
                <Select
                  value={draftSettings.web_fetch?.jina_browser_engine || 'default'}
                  onValueChange={(value) => handleJinaSettingChange('jina_browser_engine', value)}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="Select browser engine" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">Default (Balanced)</SelectItem>
                    <SelectItem value="chrome">Chrome (High Quality)</SelectItem>
                    <SelectItem value="lightweight">Lightweight (Fast)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Browser engine affects quality, speed, and completeness of content extraction.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="content-format" className="text-sm">Content Format</Label>
                <Select
                  value={draftSettings.web_fetch?.jina_content_format || 'default'}
                  onValueChange={(value) => handleJinaSettingChange('jina_content_format', value)}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="Select content format" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">Default (Markdown)</SelectItem>
                    <SelectItem value="json">JSON (Structured)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Response format for extracted content.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="timeout" className="text-sm">Timeout (seconds)</Label>
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
                  Maximum page load wait time (5-60 seconds).
                </p>
              </div>

              <div className="space-y-3 pt-2">
                <Label className="text-sm">Content Processing Options</Label>
                
                <div className="flex items-center space-x-2">
                  <Switch
                    id="gather-links"
                    checked={draftSettings.web_fetch?.jina_gather_links || false}
                    onCheckedChange={(checked) => handleJinaSettingChange('jina_gather_links', checked)}
                  />
                  <Label htmlFor="gather-links" className="text-sm font-normal cursor-pointer">
                    Gather all links at the end
                  </Label>
                </div>

                <div className="flex items-center space-x-2">
                  <Switch
                    id="gather-images"
                    checked={draftSettings.web_fetch?.jina_gather_images || false}
                    onCheckedChange={(checked) => handleJinaSettingChange('jina_gather_images', checked)}
                  />
                  <Label htmlFor="gather-images" className="text-sm font-normal cursor-pointer">
                    Gather all images at the end
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
            Webpage Fetching Provider Comparison
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-3 gap-2">
              <div className="font-medium">Feature</div>
              <div className="font-medium">Built-in</div>
              <div className="font-medium">Jina Reader</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>JavaScript Rendering</div>
              <div className="text-muted-foreground">Limited</div>
              <div className="text-green-600">Full browser</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>PDF Support</div>
              <div className="text-green-600">Native</div>
              <div className="text-green-600">Supported</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>Caching</div>
              <div className="text-green-600">Local cache</div>
              <div className="text-muted-foreground">No cache</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>API Cost</div>
              <div className="text-green-600">Free</div>
              <div className="text-orange-600">Rate limited/Paid</div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>Content Quality</div>
              <div className="text-muted-foreground">Good</div>
              <div className="text-green-600">Excellent</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}