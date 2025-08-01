import React from 'react'
import { useSettingsStore } from './SettingsStore'
// import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Label } from '../../../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select'
import { Globe, Settings, Construction } from 'lucide-react'

export const SearchSettingsTab: React.FC = () => {
  const { draftSettings, setDraftSettings } = useSettingsStore()

  const handleProviderChange = (provider: 'tavily' | 'linkup' | 'searxng') => {
    if (!draftSettings) return
    
    const newSearch = {
      ...draftSettings.search,
      provider
    }
    
    setDraftSettings({ search: newSearch })
  }

  const handleApiKeyChange = (field: string, value: string) => {
    if (!draftSettings) return
    
    const newSearch = {
      ...draftSettings.search,
      [field]: value
    }
    
    setDraftSettings({ search: newSearch })
  }

  if (!draftSettings) {
    return <div>Loading...</div>
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Globe className="h-4 w-4" />
            Search Provider Configuration
          </CardTitle>
          <CardDescription className="text-sm">
            Configure your search provider for web research capabilities.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-sm font-medium">Search Provider</Label>
              <Select
                value={draftSettings.search.provider}
                onValueChange={handleProviderChange}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Select search provider" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tavily">Tavily</SelectItem>
                  <SelectItem value="linkup">LinkUp</SelectItem>
                  <SelectItem value="searxng">SearXNG</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {draftSettings.search.provider === 'tavily' && (
              <div className="space-y-3 pl-3 border-l-2 border-blue-200 bg-blue-50/30 rounded-r-lg p-3">
                <p className="text-xs text-gray-600 mb-2">
                  AI-powered search with real-time web data and citations.
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="tavily-api-key" className="text-sm">Tavily API Key</Label>
                  <Input
                    id="tavily-api-key"
                    type="password"
                    value={draftSettings.search.tavily_api_key || ''}
                    onChange={(e) => handleApiKeyChange('tavily_api_key', e.target.value)}
                    placeholder="tvly-..."
                    className="h-8 text-sm"
                  />
                </div>
                <p className="text-xs text-gray-500">
                  Get your API key from{' '}
                  <a 
                    href="https://app.tavily.com/home" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    Tavily Dashboard
                  </a>
                </p>
              </div>
            )}

            {draftSettings.search.provider === 'linkup' && (
              <div className="space-y-3 pl-3 border-l-2 border-green-200 bg-green-50/30 rounded-r-lg p-3">
                <p className="text-xs text-gray-600 mb-2">
                  Real-time search API with comprehensive web coverage.
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="linkup-api-key" className="text-sm">LinkUp API Key</Label>
                  <Input
                    id="linkup-api-key"
                    type="password"
                    value={draftSettings.search.linkup_api_key || ''}
                    onChange={(e) => handleApiKeyChange('linkup_api_key', e.target.value)}
                    placeholder="7a8d9e1b-..."
                    className="h-8 text-sm"
                  />
                </div>
                <p className="text-xs text-gray-500">
                  Get your API key from{' '}
                  <a 
                    href="https://linkup.com/dashboard" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    LinkUp Dashboard
                  </a>
                </p>
              </div>
            )}

            {draftSettings.search.provider === 'searxng' && (
              <div className="space-y-3 pl-3 border-l-2 border-purple-200 bg-purple-50/30 rounded-r-lg p-3">
                <p className="text-xs text-gray-600 mb-2">
                  Open-source metasearch engine that aggregates results from multiple search engines.
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="searxng-base-url" className="text-sm">SearXNG Base URL</Label>
                  <Input
                    id="searxng-base-url"
                    type="url"
                    value={draftSettings.search.searxng_base_url || ''}
                    onChange={(e) => handleApiKeyChange('searxng_base_url', e.target.value)}
                    placeholder="https://your-searxng-instance.com"
                    className="h-8 text-sm"
                  />
                </div>
                <p className="text-xs text-gray-500">
                  Enter the URL of your SearXNG instance. You can use a public instance or{' '}
                  <a 
                    href="https://docs.searxng.org/" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-purple-600 hover:underline"
                  >
                    deploy your own
                  </a>
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Search Configuration
          </CardTitle>
          <CardDescription className="text-sm">
            Configure search behavior and parameters.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <Construction className="h-4 w-4 text-gray-500 mr-2" />
            <div className="text-sm text-gray-600 dark:text-gray-400">
              Advanced search configuration options will be available in future updates.
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
