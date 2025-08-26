import React from 'react'
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from './SettingsStore'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Label } from '../../../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select'
import { Globe, Settings, ChevronDown } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { Checkbox } from '../../../components/ui/checkbox'
import { Switch } from '../../../components/ui/switch'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../../../components/ui/dropdown-menu'

export const SearchSettingsTab: React.FC = () => {
  const { t } = useTranslation()
  const { draftSettings, setDraftSettings } = useSettingsStore()

  const SEARXNG_CATEGORIES = [
    { value: 'general', label: t('searchSettings.categories.general') },
    { value: 'images', label: t('searchSettings.categories.images') },
    { value: 'videos', label: t('searchSettings.categories.videos') },
    { value: 'news', label: t('searchSettings.categories.news') },
    { value: 'map', label: t('searchSettings.categories.map') },
    { value: 'music', label: t('searchSettings.categories.music') },
    { value: 'it', label: t('searchSettings.categories.it') },
    { value: 'science', label: t('searchSettings.categories.science') },
    { value: 'files', label: t('searchSettings.categories.files') },
    { value: 'social media', label: t('searchSettings.categories.socialMedia') }
  ]

  const handleProviderChange = (provider: 'tavily' | 'linkup' | 'searxng' | 'jina') => {
    if (!draftSettings) return
    
    const newSearch = {
      ...draftSettings.search,
      provider
    }
    
    setDraftSettings({ search: newSearch })
  }

  const handleApiKeyChange = (field: string, value: string | boolean) => {
    if (!draftSettings) return
    
    const newSearch = {
      ...draftSettings.search,
      [field]: value
    }
    
    setDraftSettings({ search: newSearch })
  }

  const handleCategoriesChange = (categoryValue: string, checked: boolean) => {
    if (!draftSettings) return
    
    const currentCategories = draftSettings.search.searxng_categories || 'general'
    const categoriesArray = currentCategories.split(',').map(c => c.trim()).filter(c => c)
    
    let newCategoriesArray
    if (checked) {
      newCategoriesArray = [...categoriesArray.filter(c => c !== categoryValue), categoryValue]
    } else {
      newCategoriesArray = categoriesArray.filter(c => c !== categoryValue)
    }
    
    // Ensure at least one category is selected
    if (newCategoriesArray.length === 0) {
      newCategoriesArray = ['general']
    }
    
    const newSearch = {
      ...draftSettings.search,
      searxng_categories: newCategoriesArray.join(',')
    }
    
    setDraftSettings({ search: newSearch })
  }

  const getSelectedCategories = (): string[] => {
    if (!draftSettings?.search?.searxng_categories) return ['general']
    return draftSettings.search.searxng_categories.split(',').map(c => c.trim()).filter(c => c)
  }

  const getSelectedCategoriesDisplay = (): string => {
    const selected = getSelectedCategories()
    if (selected.length === 0) return t('searchSettings.selectCategories')
    if (selected.length === 1) return SEARXNG_CATEGORIES.find(c => c.value === selected[0])?.label || selected[0]
    return t('searchSettings.categoriesSelected', { count: selected.length })
  }

  if (!draftSettings) {
    return <div>{t('searchSettings.loading')}</div>
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Globe className="h-4 w-4" />
            {t('searchSettings.providerConfiguration')}
          </CardTitle>
          <CardDescription className="text-sm">
            {t('searchSettings.providerConfigurationDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-sm font-medium">{t('searchSettings.searchProvider')}</Label>
              <Select
                value={draftSettings.search.provider}
                onValueChange={handleProviderChange}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder={t('searchSettings.selectSearchProvider')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tavily">{t('searchSettings.tavily')}</SelectItem>
                  <SelectItem value="linkup">{t('searchSettings.linkup')}</SelectItem>
                  <SelectItem value="searxng">{t('searchSettings.searxng')}</SelectItem>
                  <SelectItem value="jina">{t('searchSettings.jina')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {draftSettings.search.provider === 'tavily' && (
              <div className="space-y-3 pl-3 border-l-2 border-blue-200 bg-blue-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  {t('searchSettings.tavilyDescription')}
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="tavily-api-key" className="text-sm">{t('searchSettings.tavilyApiKey')}</Label>
                  <Input
                    id="tavily-api-key"
                    type="password"
                    value={draftSettings.search.tavily_api_key || ''}
                    onChange={(e) => handleApiKeyChange('tavily_api_key', e.target.value)}
                    placeholder={t('searchSettings.tavilyApiKeyPlaceholder')}
                    className="h-8 text-sm"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.getApiKeyFrom')}{' '}
                  <a 
                    href="https://app.tavily.com/home" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    {t('searchSettings.tavilyDashboard')}
                  </a>
                </p>
              </div>
            )}

            {draftSettings.search.provider === 'linkup' && (
              <div className="space-y-3 pl-3 border-l-2 border-green-200 bg-green-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  {t('searchSettings.linkupDescription')}
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="linkup-api-key" className="text-sm">{t('searchSettings.linkupApiKey')}</Label>
                  <Input
                    id="linkup-api-key"
                    type="password"
                    value={draftSettings.search.linkup_api_key || ''}
                    onChange={(e) => handleApiKeyChange('linkup_api_key', e.target.value)}
                    placeholder={t('searchSettings.linkupApiKeyPlaceholder')}
                    className="h-8 text-sm"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.getApiKeyFrom')}{' '}
                  <a 
                    href="https://linkup.com/dashboard" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    {t('searchSettings.linkupDashboard')}
                  </a>
                </p>
              </div>
            )}

            {draftSettings.search.provider === 'jina' && (
              <div className="space-y-3 pl-3 border-l-2 border-orange-200 bg-orange-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  {t('searchSettings.jinaDescription')}
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="jina-api-key" className="text-sm">{t('searchSettings.jinaApiKey')}</Label>
                  <Input
                    id="jina-api-key"
                    type="password"
                    value={draftSettings.search.jina_api_key || ''}
                    onChange={(e) => handleApiKeyChange('jina_api_key', e.target.value)}
                    placeholder={t('searchSettings.jinaApiKeyPlaceholder')}
                    className="h-8 text-sm"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.getApiKeyFrom')}{' '}
                  <a 
                    href="https://jina.ai/reader" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-orange-600 hover:underline"
                  >
                    {t('searchSettings.jinaDashboard')}
                  </a>
                  . {t('searchSettings.jinaFreeTier')}
                </p>
              </div>
            )}

            {draftSettings.search.provider === 'searxng' && (
              <div className="space-y-3 pl-3 border-l-2 border-purple-200 bg-purple-50/30 rounded-r-lg p-3">
                <p className="text-xs text-muted-foreground-foreground mb-2">
                  {t('searchSettings.searxngDescription')}
                </p>
                <div className="space-y-1.5">
                  <Label htmlFor="searxng-base-url" className="text-sm">{t('searchSettings.searxngBaseUrl')}</Label>
                  <Input
                    id="searxng-base-url"
                    type="url"
                    value={draftSettings.search.searxng_base_url || ''}
                    onChange={(e) => handleApiKeyChange('searxng_base_url', e.target.value)}
                    placeholder={t('searchSettings.searxngBaseUrlPlaceholder')}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm">{t('searchSettings.searchCategories')}</Label>
                  <div className="relative">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="outline"
                          className="h-8 w-full justify-between text-sm"
                        >
                          {getSelectedCategoriesDisplay()}
                          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent className="w-full p-0" align="start">
                        <div className="p-3">
                          <p className="text-xs text-muted-foreground-foreground mb-3">
                            {t('searchSettings.selectCategoriesDescription')}
                          </p>
                          <div className="space-y-2">
                            {SEARXNG_CATEGORIES.map((category) => {
                              const isSelected = getSelectedCategories().includes(category.value)
                              return (
                                <DropdownMenuItem
                                  key={category.value}
                                  className="flex items-center space-x-2 cursor-pointer"
                                  onClick={(e) => {
                                    e.preventDefault()
                                    handleCategoriesChange(category.value, !isSelected)
                                  }}
                                >
                                  <Checkbox
                                    id={`category-${category.value}`}
                                    checked={isSelected}
                                    onCheckedChange={() => {}} // Prevent direct checkbox interaction since clicking the item handles it
                                  />
                                  <Label
                                    htmlFor={`category-${category.value}`}
                                    className="text-sm font-normal cursor-pointer"
                                  >
                                    {category.label}
                                  </Label>
                                </DropdownMenuItem>
                              )
                            })}
                          </div>
                        </div>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.searxngInstanceUrl')}{' '}
                  <a 
                    href="https://docs.searxng.org/" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-purple-600 hover:underline"
                  >
                    {t('searchSettings.deployYourOwn')}
                  </a>
                  <br />
                  <strong>{t('searchSettings.searxngNote')}</strong>
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Provider-specific search configuration for Tavily and LinkUp */}
      {(draftSettings.search.provider === 'tavily' || draftSettings.search.provider === 'linkup') && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Settings className="h-4 w-4" />
              {t('searchSettings.searchConfiguration')}
            </CardTitle>
            <CardDescription className="text-sm">
              {t('searchSettings.searchConfigurationDescription', { provider: draftSettings.search.provider === 'tavily' ? 'Tavily' : 'LinkUp' })}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="max-search-results" className="text-sm">{t('searchSettings.maxSearchResults')}</Label>
                <Input
                  id="max-search-results"
                  type="number"
                  min="1"
                  max="20"
                  value={draftSettings.search.max_results || 5}
                  onChange={(e) => {
                    const value = Math.max(1, Math.min(20, parseInt(e.target.value) || 5))
                    handleApiKeyChange('max_results', value.toString())
                  }}
                  className="h-8 text-sm"
                />
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.maxSearchResultsDescriptionTavily')}
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="search-depth" className="text-sm">{t('searchSettings.searchDepth')}</Label>
                <Select
                  value={draftSettings.search.search_depth || 'standard'}
                  onValueChange={(value) => handleApiKeyChange('search_depth', value)}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder={t('searchSettings.selectSearchDepth')} />
                  </SelectTrigger>
                  <SelectContent>
                    {draftSettings.search.provider === 'tavily' ? (
                      <>
                        <SelectItem value="standard">{t('searchSettings.standardBasic')}</SelectItem>
                        <SelectItem value="advanced">{t('searchSettings.advancedCredits')}</SelectItem>
                      </>
                    ) : (
                      <>
                        <SelectItem value="standard">{t('searchSettings.standardFast')}</SelectItem>
                        <SelectItem value="advanced">{t('searchSettings.deepComprehensive')}</SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {draftSettings.search.provider === 'tavily' 
                    ? t('searchSettings.tavilySearchDepthDescription')
                    : t('searchSettings.linkupSearchDepthDescription')}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Jina-specific configuration */}
      {draftSettings.search.provider === 'jina' && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Settings className="h-4 w-4" />
              {t('searchSettings.jinaSearchConfiguration')}
            </CardTitle>
            <CardDescription className="text-sm">
              {t('searchSettings.jinaSearchConfigurationDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="max-search-results-jina" className="text-sm">{t('searchSettings.maxSearchResults')}</Label>
                <Input
                  id="max-search-results-jina"
                  type="number"
                  min="1"
                  max="10"
                  value={draftSettings.search.max_results || 5}
                  onChange={(e) => {
                    const value = Math.max(1, Math.min(10, parseInt(e.target.value) || 5))
                    handleApiKeyChange('max_results', value.toString())
                  }}
                  className="h-8 text-sm"
                />
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.maxSearchResultsDescriptionJina')}
                </p>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center space-x-2">
                  <Switch
                    id="jina-read-full"
                    checked={draftSettings.search.jina_read_full_content || false}
                    onCheckedChange={(checked) => handleApiKeyChange('jina_read_full_content', checked)}
                  />
                  <Label htmlFor="jina-read-full" className="text-sm font-normal cursor-pointer">
                    {t('searchSettings.readFullContent')}
                  </Label>
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.readFullContentDescription')}
                </p>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center space-x-2">
                  <Switch
                    id="jina-fetch-favicons"
                    checked={draftSettings.search.jina_fetch_favicons || false}
                    onCheckedChange={(checked) => handleApiKeyChange('jina_fetch_favicons', checked)}
                  />
                  <Label htmlFor="jina-fetch-favicons" className="text-sm font-normal cursor-pointer">
                    {t('searchSettings.fetchFavicons')}
                  </Label>
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.fetchFaviconsDescription')}
                </p>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center space-x-2">
                  <Switch
                    id="jina-bypass-cache"
                    checked={draftSettings.search.jina_bypass_cache || false}
                    onCheckedChange={(checked) => handleApiKeyChange('jina_bypass_cache', checked)}
                  />
                  <Label htmlFor="jina-bypass-cache" className="text-sm font-normal cursor-pointer">
                    {t('searchSettings.bypassCache')}
                  </Label>
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('searchSettings.bypassCacheDescription')}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* SearXNG-specific configuration */}
      {draftSettings.search.provider === 'searxng' && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Settings className="h-4 w-4" />
              {t('searchSettings.searxngConfiguration')}
            </CardTitle>
            <CardDescription className="text-sm">
              {t('searchSettings.searxngConfigurationDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="max-search-results" className="text-sm">{t('searchSettings.maxSearchResults')}</Label>
              <Input
                id="max-search-results"
                type="number"
                min="1"
                max="20"
                value={draftSettings.search.max_results || 5}
                onChange={(e) => {
                  const value = Math.max(1, Math.min(20, parseInt(e.target.value) || 5))
                  handleApiKeyChange('max_results', value.toString())
                }}
                className="h-8 text-sm"
              />
              <p className="text-xs text-muted-foreground">
                {t('searchSettings.maxSearchResultsDescriptionSearxng')}
              </p>
            </div>
            <p className="text-xs text-muted-foreground">
              {t('searchSettings.searxngNoApiCosts')}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
