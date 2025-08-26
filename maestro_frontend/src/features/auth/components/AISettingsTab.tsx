import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from './SettingsStore'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Label } from '../../../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select'
import { Combobox } from '../../../components/ui/combobox'
import { AlertCircle, CheckCircle, Loader2, AlertTriangle, Settings, Target, Zap, Scale, Brain, CheckSquare, ToggleLeft, ToggleRight, RefreshCw } from 'lucide-react'

type ProviderKey = 'openrouter' | 'openai' | 'custom'
type ModelType = 'fast' | 'mid' | 'intelligent' | 'verifier'

export const AISettingsTab: React.FC = () => {
  const { t } = useTranslation()
  const { 
    draftSettings, 
    setDraftSettings, 
    isTestingConnection, 
    connectionTestResult, 
    testConnection, 
    fetchAvailableModels, 
    modelsByProvider,
    modelsFetchError,
    clearModels,
    clearModelsFetchError
  } = useSettingsStore()
  const [testProvider, setTestProvider] = useState<string | null>(null)
  const [refreshingModels, setRefreshingModels] = useState<string | null>(null)
  const [editingApiKey, setEditingApiKey] = useState<{[key: string]: boolean}>({})

  // Helper function to display partial API key
  const formatApiKeyDisplay = (apiKey: string | null): string => {
    if (!apiKey || apiKey.length < 6) return apiKey || ''
    return '•'.repeat(Math.max(0, apiKey.length - 6)) + apiKey.slice(-6)
  }

  // Helper function to handle API key input focus
  const handleApiKeyFocus = (fieldKey: string) => {
    setEditingApiKey(prev => ({ ...prev, [fieldKey]: true }))
  }

  // Helper function to handle API key input blur
  const handleApiKeyBlur = (fieldKey: string) => {
    setEditingApiKey(prev => ({ ...prev, [fieldKey]: false }))
  }

  // Helper function to refresh models for a specific provider
  const handleRefreshModels = async (provider?: string) => {
    setRefreshingModels(provider || 'default')
    try {
      await fetchAvailableModels(provider)
    } finally {
      setRefreshingModels(null)
    }
  }

  // Helper function to get models for a specific provider
  const getModelsForProvider = (provider: string): string[] => {
    return modelsByProvider[provider] || []
  }

  // Helper function to get models for a model type in advanced mode
  const getModelsForModelType = (modelType: ModelType): string[] => {
    if (!draftSettings) return []
    const provider = draftSettings.ai_endpoints.advanced_models[modelType].provider
    return getModelsForProvider(provider)
  }

  // Helper function to get models for simple mode (all use the same provider)
  const getModelsForSimpleMode = (): string[] => {
    const enabledProvider = getEnabledProvider()
    return enabledProvider ? getModelsForProvider(enabledProvider) : []
  }

  useEffect(() => {
    // Only fetch models in simple mode and when component mounts with an enabled provider
    // Don't auto-fetch when switching to advanced mode to avoid authentication issues
    if (draftSettings?.ai_endpoints && !draftSettings.ai_endpoints.advanced_mode) {
      const enabledProvider = Object.entries(draftSettings.ai_endpoints.providers).find(
        ([_, config]) => config.enabled
      )
      
      if (enabledProvider && getModelsForSimpleMode().length === 0) {
        const providerConfig = draftSettings.ai_endpoints.providers[enabledProvider[0] as ProviderKey]
        // Only fetch models if we have an API key configured (except for custom providers)
        if (providerConfig?.api_key || enabledProvider[0] === 'custom') {
          fetchAvailableModels(enabledProvider[0])
        }
      }
    }
  }, [draftSettings?.ai_endpoints, fetchAvailableModels])

  const getEnabledProvider = (): ProviderKey | null => {
    if (!draftSettings) return null
    return Object.entries(draftSettings.ai_endpoints.providers).find(
      ([_, config]) => config.enabled
    )?.[0] as ProviderKey || null
  }

  const handleProviderChange = (provider: ProviderKey) => {
    if (!draftSettings) return
    
    // Clear models and errors when provider changes
    clearModels()
    clearModelsFetchError()
    
    const newAiEndpoints = {
      ...draftSettings.ai_endpoints,
      providers: {
        ...draftSettings.ai_endpoints.providers,
        // Disable all providers first
        openrouter: { ...draftSettings.ai_endpoints.providers.openrouter, enabled: false },
        openai: { ...draftSettings.ai_endpoints.providers.openai, enabled: false },
        custom: { ...draftSettings.ai_endpoints.providers.custom, enabled: false },
        // Enable the selected provider
        [provider]: {
          ...(draftSettings.ai_endpoints.providers[provider] as any),
          enabled: true
        }
      }
    }
    
    // In simple mode, auto-populate all models with the new provider's config
    if (!draftSettings.ai_endpoints.advanced_mode) {
      const providerConfig = newAiEndpoints.providers[provider] as any
      const baseUrl = providerConfig.base_url || (provider === 'openrouter' ? 'https://openrouter.ai/api/v1/' : 
                                                   provider === 'openai' ? 'https://api.openai.com/v1/' : '')
      
      newAiEndpoints.advanced_models = {
        fast: {
          provider,
          api_key: providerConfig.api_key,
          base_url: baseUrl,
          model_name: ''  // Clear model name when provider changes
        },
        mid: {
          provider,
          api_key: providerConfig.api_key,
          base_url: baseUrl,
          model_name: ''  // Clear model name when provider changes
        },
        intelligent: {
          provider,
          api_key: providerConfig.api_key,
          base_url: baseUrl,
          model_name: ''  // Clear model name when provider changes
        },
        verifier: {
          provider,
          api_key: providerConfig.api_key,
          base_url: baseUrl,
          model_name: ''  // Clear model name when provider changes
        }
      }
    }
    
    setDraftSettings({ ai_endpoints: newAiEndpoints })
  }

  const handleApiKeyChange = (field: string, value: string) => {
    if (!draftSettings) return
    
    const enabledProvider = getEnabledProvider()
    if (!enabledProvider) return

    const newAiEndpoints = {
      ...draftSettings.ai_endpoints,
      providers: {
        ...draftSettings.ai_endpoints.providers,
        [enabledProvider]: {
          ...(draftSettings.ai_endpoints.providers[enabledProvider] as any),
          [field]: value
        }
      }
    }

    // In simple mode, sync the API key/base URL to all models
    if (!draftSettings.ai_endpoints.advanced_mode) {
      newAiEndpoints.advanced_models = {
        fast: {
          ...draftSettings.ai_endpoints.advanced_models.fast,
          [field]: value,
          provider: enabledProvider
        },
        mid: {
          ...draftSettings.ai_endpoints.advanced_models.mid,
          [field]: value,
          provider: enabledProvider
        },
        intelligent: {
          ...draftSettings.ai_endpoints.advanced_models.intelligent,
          [field]: value,
          provider: enabledProvider
        },
        verifier: {
          ...draftSettings.ai_endpoints.advanced_models.verifier,
          [field]: value,
          provider: enabledProvider
        }
      }
    }

    setDraftSettings({ ai_endpoints: newAiEndpoints })
  }

  const handleModelChange = (modelType: ModelType, model: string) => {
    if (!draftSettings) return
    
    const newAiEndpoints = {
      ...draftSettings.ai_endpoints,
      advanced_models: {
        ...draftSettings.ai_endpoints.advanced_models,
        [modelType]: {
          ...draftSettings.ai_endpoints.advanced_models[modelType],
          model_name: model
        }
      }
    }
    
    setDraftSettings({ ai_endpoints: newAiEndpoints })
  }

  const handleAdvancedModeToggle = () => {
    if (!draftSettings) return
    
    const newAdvancedMode = !draftSettings.ai_endpoints.advanced_mode
    const enabledProvider = getEnabledProvider()
    
    let newAiEndpoints = {
      ...draftSettings.ai_endpoints,
      advanced_mode: newAdvancedMode
    }
    
    // If switching TO simple mode, sync all models to use the primary provider
    if (!newAdvancedMode && enabledProvider) {
      const providerConfig = draftSettings.ai_endpoints.providers[enabledProvider] as any
      const baseUrl = providerConfig.base_url || (enabledProvider === 'openrouter' ? 'https://openrouter.ai/api/v1/' : 
                                                   enabledProvider === 'openai' ? 'https://api.openai.com/v1/' : '')
      
      newAiEndpoints.advanced_models = {
        fast: {
          provider: enabledProvider,
          api_key: providerConfig.api_key,
          base_url: baseUrl,
          model_name: draftSettings.ai_endpoints.advanced_models.fast.model_name
        },
        mid: {
          provider: enabledProvider,
          api_key: providerConfig.api_key,
          base_url: baseUrl,
          model_name: draftSettings.ai_endpoints.advanced_models.mid.model_name
        },
        intelligent: {
          provider: enabledProvider,
          api_key: providerConfig.api_key,
          base_url: baseUrl,
          model_name: draftSettings.ai_endpoints.advanced_models.intelligent.model_name
        },
        verifier: {
          provider: enabledProvider,
          api_key: providerConfig.api_key,
          base_url: baseUrl,
          model_name: draftSettings.ai_endpoints.advanced_models.verifier.model_name
        }
      }
    }
    
    setDraftSettings({ ai_endpoints: newAiEndpoints })
  }

  const handleAdvancedModelChange = (modelType: ModelType, field: string, value: string) => {
    if (!draftSettings) return
    
    let updatedModel = {
      ...draftSettings.ai_endpoints.advanced_models[modelType],
      [field]: value
    }
    
    // If changing provider, auto-update base_url, restore saved API key, clear model name, and fetch new models
    if (field === 'provider') {
      // Clear models and errors when provider changes
      clearModels()
      clearModelsFetchError()
      
      const defaultBaseUrls = {
        openrouter: 'https://openrouter.ai/api/v1/',
        openai: 'https://api.openai.com/v1/',
        custom: ''
      }
      
      updatedModel.base_url = defaultBaseUrls[value as ProviderKey] || ''
      updatedModel.model_name = ''  // Clear model name when provider changes
      
      // Restore saved API key for this provider if available
      const savedProviderConfig = draftSettings.ai_endpoints.providers[value as ProviderKey]
      if (savedProviderConfig?.api_key) {
        updatedModel.api_key = savedProviderConfig.api_key
      }
      
      // Update the settings first
      const newAiEndpoints = {
        ...draftSettings.ai_endpoints,
        advanced_models: {
          ...draftSettings.ai_endpoints.advanced_models,
          [modelType]: updatedModel
        }
      }
      
      setDraftSettings({ ai_endpoints: newAiEndpoints })
      
      // Only fetch models if we have an API key for this provider (or it's custom)
      setTimeout(() => {
        const hasApiKey = updatedModel.api_key || value === 'custom'
        if (hasApiKey) {
          fetchAvailableModels(value as ProviderKey)
        }
      }, 100)
      
      return
    }
    
    // If changing API key, also save it to the provider config for future use
    if (field === 'api_key') {
      const currentProvider = updatedModel.provider as ProviderKey
      const newAiEndpoints = {
        ...draftSettings.ai_endpoints,
        providers: {
          ...draftSettings.ai_endpoints.providers,
          [currentProvider]: {
            ...draftSettings.ai_endpoints.providers[currentProvider],
            api_key: value
          }
        },
        advanced_models: {
          ...draftSettings.ai_endpoints.advanced_models,
          [modelType]: updatedModel
        }
      }
      
      setDraftSettings({ ai_endpoints: newAiEndpoints })
      return
    }
    
    const newAiEndpoints = {
      ...draftSettings.ai_endpoints,
      advanced_models: {
        ...draftSettings.ai_endpoints.advanced_models,
        [modelType]: updatedModel
      }
    }
    
    setDraftSettings({ ai_endpoints: newAiEndpoints })
  }

  const handleTestConnection = async () => {
    const enabledProvider = getEnabledProvider()
    if (!draftSettings || !enabledProvider) return
    
    const providerConfig = draftSettings.ai_endpoints.providers[enabledProvider] as any
    if (!providerConfig.api_key) {
      setTestProvider(enabledProvider)
      return
    }
    
    setTestProvider(enabledProvider)
    await testConnection(enabledProvider, providerConfig.api_key, providerConfig.base_url || undefined)
  }

  if (!draftSettings) {
    return <div>{t('aiSettings.loading')}</div>
  }

  const enabledProvider = getEnabledProvider()
  const currentProviderConfig = enabledProvider ? draftSettings.ai_endpoints.providers[enabledProvider] as any : null

  return (
    <div className="space-y-4">
      {/* Advanced Mode Toggle */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Settings className="h-4 w-4" />
            {t('aiSettings.advancedConfiguration')}
          </CardTitle>
          <CardDescription className="text-sm">
            {t('aiSettings.advancedConfigurationDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <Label className="text-sm font-medium">{t('aiSettings.advancedMode')}</Label>
              <p className="text-xs text-muted-foreground">
                {t('aiSettings.advancedModeDescription')}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleAdvancedModeToggle}
              className="p-2"
            >
              {draftSettings.ai_endpoints.advanced_mode ? (
                <ToggleRight className="h-5 w-5 text-blue-600" />
              ) : (
                <ToggleLeft className="h-5 w-5 text-muted" />
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Simple Mode Configuration */}
      {!draftSettings.ai_endpoints.advanced_mode && (
        <>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Settings className="h-4 w-4" />
                {t('aiSettings.providerConfiguration')}
              </CardTitle>
              <CardDescription className="text-sm">
                {t('aiSettings.providerConfigurationDescription')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">{t('aiSettings.aiProvider')}</Label>
                  <Select
                    value={enabledProvider || ''}
                    onValueChange={handleProviderChange}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue placeholder={t('aiSettings.selectAiProvider')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openrouter">{t('aiSettings.openRouter')}</SelectItem>
                      <SelectItem value="openai">{t('aiSettings.openAiApi')}</SelectItem>
                      <SelectItem value="custom">{t('aiSettings.customProvider')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {enabledProvider === 'openrouter' && (
                  <div className="space-y-3 pl-3 border-l-2 border-blue-200 bg-blue-50/30 rounded-r-lg p-3">
                    <p className="text-xs text-muted-foreground mb-2">
                      {t('aiSettings.openRouterDescription')}
                    </p>
                    <div className="grid grid-cols-1 gap-3">
                      <div className="space-y-1.5">
                        <Label htmlFor="api-key" className="text-sm">{t('aiSettings.apiKey')}</Label>
                        <div className="flex gap-2">
                          <Input
                            id="api-key"
                            type="password"
                            value={currentProviderConfig?.api_key || ''}
                            onChange={(e) => handleApiKeyChange('api_key', e.target.value)}
                            placeholder={t('aiSettings.openRouterApiKeyPlaceholder')}
                            className="h-8 text-sm"
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleTestConnection}
                            disabled={isTestingConnection && testProvider === enabledProvider}
                            className="h-8 px-3"
                          >
                            {isTestingConnection && testProvider === enabledProvider ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              t('aiSettings.test')
                            )}
                          </Button>
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="base-url" className="text-sm">{t('aiSettings.baseUrl')}</Label>
                        <Input
                          id="base-url"
                          value={currentProviderConfig?.base_url || ''}
                          onChange={(e) => handleApiKeyChange('base_url', e.target.value)}
                          placeholder={t('aiSettings.openRouterBaseUrlPlaceholder')}
                          className="h-8 text-sm"
                        />
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {t('aiSettings.getApiKeyFrom')}{' '}
                      <a 
                        href="https://openrouter.ai/keys" 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline"
                      >
                        {t('aiSettings.openRouterDashboard')}
                      </a>
                    </p>
                  </div>
                )}

                {enabledProvider === 'openai' && (
                  <div className="space-y-3 pl-3 border-l-2 border-green-200 bg-green-50/30 rounded-r-lg p-3">
                    <p className="text-xs text-muted-foreground mb-2">
                      {t('aiSettings.openAiDescription')}
                    </p>
                    <div className="grid grid-cols-1 gap-3">
                      <div className="space-y-1.5">
                        <Label htmlFor="api-key" className="text-sm">{t('aiSettings.apiKey')}</Label>
                        <div className="flex gap-2">
                          <Input
                            id="api-key"
                            type="password"
                            value={currentProviderConfig?.api_key || ''}
                            onChange={(e) => handleApiKeyChange('api_key', e.target.value)}
                            placeholder={t('aiSettings.openAiApiKeyPlaceholder')}
                            className="h-8 text-sm"
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleTestConnection}
                            disabled={isTestingConnection && testProvider === enabledProvider}
                            className="h-8 px-3"
                          >
                            {isTestingConnection && testProvider === enabledProvider ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              t('aiSettings.test')
                            )}
                          </Button>
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="base-url" className="text-sm">{t('aiSettings.baseUrl')}</Label>
                        <Input
                          id="base-url"
                          value={currentProviderConfig?.base_url || ''}
                          onChange={(e) => handleApiKeyChange('base_url', e.target.value)}
                          placeholder={t('aiSettings.openAiBaseUrlPlaceholder')}
                          className="h-8 text-sm"
                        />
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {t('aiSettings.getApiKeyFrom')}{' '}
                      <a 
                        href="https://platform.openai.com/api-keys" 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline"
                      >
                        {t('aiSettings.openAiPlatform')}
                      </a>
                    </p>
                  </div>
                )}

                {enabledProvider === 'custom' && (
                  <div className="space-y-3 pl-3 border-l-2 border-purple-200 bg-purple-50/30 rounded-r-lg p-3">
                    <p className="text-xs text-muted-foreground mb-2">
                      {t('aiSettings.customProviderDescription')}
                    </p>
                    <div className="grid grid-cols-1 gap-3">
                      <div className="space-y-1.5">
                        <Label htmlFor="api-key" className="text-sm">{t('aiSettings.apiKey')}</Label>
                        <div className="flex gap-2">
                          <Input
                            id="api-key"
                            type="password"
                            value={currentProviderConfig?.api_key || ''}
                            onChange={(e) => handleApiKeyChange('api_key', e.target.value)}
                            placeholder={t('aiSettings.apiKeyOptional')}
                            className="h-8 text-sm"
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleTestConnection}
                            disabled={isTestingConnection && testProvider === enabledProvider}
                            className="h-8 px-3"
                          >
                            {isTestingConnection && testProvider === enabledProvider ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              t('aiSettings.test')
                            )}
                          </Button>
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="base-url" className="text-sm">{t('aiSettings.baseUrl')}</Label>
                        <Input
                          id="base-url"
                          value={currentProviderConfig?.base_url || ''}
                          onChange={(e) => handleApiKeyChange('base_url', e.target.value)}
                          placeholder={t('aiSettings.customBaseUrlPlaceholder')}
                          className="h-8 text-sm"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Connection Test Result */}
              {connectionTestResult && testProvider && (
                <Card className={connectionTestResult.success ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}>
                  <CardContent className="p-4">
                    <div className="flex items-center">
                      {connectionTestResult.success ? (
                        <CheckCircle className="h-5 w-5 text-green-500 mr-2" />
                      ) : (
                        <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
                      )}
                      <span className={connectionTestResult.success ? "text-green-700" : "text-red-700"}>
                        {connectionTestResult.message}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              )}
            </CardContent>
          </Card>

          {/* Model Selection */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Target className="h-4 w-4" />
                {t('aiSettings.modelSelection')}
              </CardTitle>
              <CardDescription className="text-sm">
                {t('aiSettings.modelSelectionDescription')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!enabledProvider ? (
                <div className="flex items-center p-3 bg-yellow-50 rounded-lg">
                  <AlertTriangle className="h-4 w-4 text-yellow-500 mr-2" />
                  <span className="text-yellow-700 text-sm">
                    {t('aiSettings.selectProviderToConfigure')}
                  </span>
                </div>
              ) : (
                <>
                  {/* Models Fetch Error */}
                  {modelsFetchError && (
                    <Card className="bg-red-50 border-red-200">
                      <CardContent className="p-4">
                        <div className="flex items-center">
                          <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
                          <span className="text-red-700 text-sm">
                            {modelsFetchError}
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={clearModelsFetchError}
                            className="ml-auto h-6 w-6 p-0"
                          >
                            ×
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium flex items-center gap-2">
                        <Zap className="h-4 w-4" />
                        {t('aiSettings.fastModel')}
                      </Label>
                      <Combobox
                        value={draftSettings.ai_endpoints.advanced_models.fast.model_name}
                        onValueChange={(value) => handleModelChange('fast', value)}
                        options={getModelsForSimpleMode()}
                        placeholder={t('aiSettings.quickResponses')}
                      />
                      <p className="text-xs text-muted-foreground-foreground">{t('aiSettings.fastModelDescription')}</p>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium flex items-center gap-2">
                        <Scale className="h-4 w-4" />
                        {t('aiSettings.midModel')}
                      </Label>
                      <Combobox
                        value={draftSettings.ai_endpoints.advanced_models.mid.model_name}
                        onValueChange={(value) => handleModelChange('mid', value)}
                        options={getModelsForSimpleMode()}
                      />
                      <p className="text-xs text-muted-foreground">{t('aiSettings.midModelDescription')}</p>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium flex items-center gap-2">
                        <Brain className="h-4 w-4" />
                        {t('aiSettings.intelligentModel')}
                      </Label>
                      <Combobox
                        value={draftSettings.ai_endpoints.advanced_models.intelligent.model_name}
                        onValueChange={(value) => handleModelChange('intelligent', value)}
                        options={getModelsForSimpleMode()}
                      />
                      <p className="text-xs text-muted-foreground">{t('aiSettings.intelligentModelDescription')}</p>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium flex items-center gap-2">
                        <CheckSquare className="h-4 w-4" />
                        {t('aiSettings.verifierModel')}
                      </Label>
                      <Combobox
                        value={draftSettings.ai_endpoints.advanced_models.verifier.model_name}
                        onValueChange={(value) => handleModelChange('verifier', value)}
                        options={getModelsForSimpleMode()}
                      />
                      <p className="text-xs text-muted-foreground">{t('aiSettings.verifierModelDescription')}</p>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Advanced Model Configuration */}
      {draftSettings.ai_endpoints.advanced_mode && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="h-4 w-4" />
              {t('aiSettings.advancedModelConfiguration')}
            </CardTitle>
            <CardDescription className="text-sm">
              {t('aiSettings.advancedModelConfigurationDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Models Fetch Error for Advanced Mode */}
            {modelsFetchError && (
              <Card className="bg-red-50 border-red-200">
                <CardContent className="p-4">
                  <div className="flex items-center">
                    <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
                    <span className="text-red-700 text-sm">
                      {modelsFetchError}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={clearModelsFetchError}
                      className="ml-auto h-6 w-6 p-0"
                    >
                      ×
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
            {/* Fast Model Configuration */}
            <div className="space-y-3 p-4 border rounded-lg">
              <div className="flex items-center gap-2 mb-3">
                <Zap className="h-4 w-4" />
                <Label className="text-sm font-medium">{t('aiSettings.fastModelConfiguration')}</Label>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.provider')}</Label>
                  <Select
                    value={draftSettings.ai_endpoints.advanced_models.fast.provider}
                    onValueChange={(value) => handleAdvancedModelChange('fast', 'provider', value)}
                  >
                    <SelectTrigger className="h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openrouter">{t('aiSettings.openRouter')}</SelectItem>
                      <SelectItem value="openai">{t('aiSettings.openAiApi')}</SelectItem>
                      <SelectItem value="custom">{t('aiSettings.customProvider')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs flex items-center justify-between">
                    {t('aiSettings.modelName')}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRefreshModels(draftSettings.ai_endpoints.advanced_models.fast.provider)}
                      disabled={refreshingModels === draftSettings.ai_endpoints.advanced_models.fast.provider}
                      className="h-6 w-6 p-0"
                    >
                      {refreshingModels === draftSettings.ai_endpoints.advanced_models.fast.provider ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3" />
                      )}
                    </Button>
                  </Label>
                  <Combobox
                    value={draftSettings.ai_endpoints.advanced_models.fast.model_name}
                    onValueChange={(value) => handleAdvancedModelChange('fast', 'model_name', value)}
                    options={getModelsForModelType('fast')}
                    placeholder={t('aiSettings.selectModel')}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.apiKey')}</Label>
                  <Input
                    type={editingApiKey['fast-api-key'] ? 'text' : 'password'}
                    value={editingApiKey['fast-api-key'] ? 
                      (draftSettings.ai_endpoints.advanced_models.fast.api_key || '') : 
                      formatApiKeyDisplay(draftSettings.ai_endpoints.advanced_models.fast.api_key)
                    }
                    onChange={(e) => handleAdvancedModelChange('fast', 'api_key', e.target.value)}
                    onFocus={() => handleApiKeyFocus('fast-api-key')}
                    onBlur={() => handleApiKeyBlur('fast-api-key')}
                    placeholder={t('aiSettings.apiKeyOptional')}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.baseUrl')}</Label>
                  <Input
                    value={draftSettings.ai_endpoints.advanced_models.fast.base_url}
                    onChange={(e) => handleAdvancedModelChange('fast', 'base_url', e.target.value)}
                    placeholder={t('aiSettings.baseUrl')}
                    className="h-8 text-sm"
                  />
                </div>
              </div>
            </div>

            {/* Mid Model Configuration */}
            <div className="space-y-3 p-4 border rounded-lg">
              <div className="flex items-center gap-2 mb-3">
                <Scale className="h-4 w-4" />
                <Label className="text-sm font-medium">{t('aiSettings.midModelConfiguration')}</Label>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.provider')}</Label>
                  <Select
                    value={draftSettings.ai_endpoints.advanced_models.mid.provider}
                    onValueChange={(value) => handleAdvancedModelChange('mid', 'provider', value)}
                  >
                    <SelectTrigger className="h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openrouter">{t('aiSettings.openRouter')}</SelectItem>
                      <SelectItem value="openai">{t('aiSettings.openAiApi')}</SelectItem>
                      <SelectItem value="custom">{t('aiSettings.customProvider')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs flex items-center justify-between">
                    {t('aiSettings.modelName')}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRefreshModels(draftSettings.ai_endpoints.advanced_models.mid.provider)}
                      disabled={refreshingModels === draftSettings.ai_endpoints.advanced_models.mid.provider}
                      className="h-6 w-6 p-0"
                    >
                      {refreshingModels === draftSettings.ai_endpoints.advanced_models.mid.provider ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3" />
                      )}
                    </Button>
                  </Label>
                  <Combobox
                    value={draftSettings.ai_endpoints.advanced_models.mid.model_name}
                    onValueChange={(value) => handleAdvancedModelChange('mid', 'model_name', value)}
                    options={getModelsForModelType('mid')}
                    placeholder={t('aiSettings.selectModel')}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.apiKey')}</Label>
                  <Input
                    type={editingApiKey['mid-api-key'] ? 'text' : 'password'}
                    value={editingApiKey['mid-api-key'] ? 
                      (draftSettings.ai_endpoints.advanced_models.mid.api_key || '') : 
                      formatApiKeyDisplay(draftSettings.ai_endpoints.advanced_models.mid.api_key)
                    }
                    onChange={(e) => handleAdvancedModelChange('mid', 'api_key', e.target.value)}
                    onFocus={() => handleApiKeyFocus('mid-api-key')}
                    onBlur={() => handleApiKeyBlur('mid-api-key')}
                    placeholder={t('aiSettings.apiKeyOptional')}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.baseUrl')}</Label>
                  <Input
                    value={draftSettings.ai_endpoints.advanced_models.mid.base_url}
                    onChange={(e) => handleAdvancedModelChange('mid', 'base_url', e.target.value)}
                    placeholder={t('aiSettings.baseUrl')}
                    className="h-8 text-sm"
                  />
                </div>
              </div>
            </div>

            {/* Intelligent Model Configuration */}
            <div className="space-y-3 p-4 border rounded-lg">
              <div className="flex items-center gap-2 mb-3">
                <Brain className="h-4 w-4" />
                <Label className="text-sm font-medium">{t('aiSettings.intelligentModelConfiguration')}</Label>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.provider')}</Label>
                  <Select
                    value={draftSettings.ai_endpoints.advanced_models.intelligent.provider}
                    onValueChange={(value) => handleAdvancedModelChange('intelligent', 'provider', value)}
                  >
                    <SelectTrigger className="h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openrouter">{t('aiSettings.openRouter')}</SelectItem>
                      <SelectItem value="openai">{t('aiSettings.openAiApi')}</SelectItem>
                      <SelectItem value="custom">{t('aiSettings.customProvider')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs flex items-center justify-between">
                    {t('aiSettings.modelName')}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRefreshModels(draftSettings.ai_endpoints.advanced_models.intelligent.provider)}
                      disabled={refreshingModels === draftSettings.ai_endpoints.advanced_models.intelligent.provider}
                      className="h-6 w-6 p-0"
                    >
                      {refreshingModels === draftSettings.ai_endpoints.advanced_models.intelligent.provider ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3" />
                      )}
                    </Button>
                  </Label>
                  <Combobox
                    value={draftSettings.ai_endpoints.advanced_models.intelligent.model_name}
                    onValueChange={(value) => handleAdvancedModelChange('intelligent', 'model_name', value)}
                    options={getModelsForModelType('intelligent')}
                    placeholder={t('aiSettings.selectModel')}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.apiKey')}</Label>
                  <Input
                    type={editingApiKey['intelligent-api-key'] ? 'text' : 'password'}
                    value={editingApiKey['intelligent-api-key'] ? 
                      (draftSettings.ai_endpoints.advanced_models.intelligent.api_key || '') : 
                      formatApiKeyDisplay(draftSettings.ai_endpoints.advanced_models.intelligent.api_key)
                    }
                    onChange={(e) => handleAdvancedModelChange('intelligent', 'api_key', e.target.value)}
                    onFocus={() => handleApiKeyFocus('intelligent-api-key')}
                    onBlur={() => handleApiKeyBlur('intelligent-api-key')}
                    placeholder={t('aiSettings.apiKeyOptional')}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.baseUrl')}</Label>
                  <Input
                    value={draftSettings.ai_endpoints.advanced_models.intelligent.base_url}
                    onChange={(e) => handleAdvancedModelChange('intelligent', 'base_url', e.target.value)}
                    placeholder={t('aiSettings.baseUrl')}
                    className="h-8 text-sm"
                  />
                </div>
              </div>
            </div>

            {/* Verifier Model Configuration */}
            <div className="space-y-3 p-4 border rounded-lg">
              <div className="flex items-center gap-2 mb-3">
                <CheckSquare className="h-4 w-4" />
                <Label className="text-sm font-medium">{t('aiSettings.verifierModelConfiguration')}</Label>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.provider')}</Label>
                  <Select
                    value={draftSettings.ai_endpoints.advanced_models.verifier.provider}
                    onValueChange={(value) => handleAdvancedModelChange('verifier', 'provider', value)}
                  >
                    <SelectTrigger className="h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openrouter">{t('aiSettings.openRouter')}</SelectItem>
                      <SelectItem value="openai">{t('aiSettings.openAiApi')}</SelectItem>
                      <SelectItem value="custom">{t('aiSettings.customProvider')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs flex items-center justify-between">
                    {t('aiSettings.modelName')}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRefreshModels(draftSettings.ai_endpoints.advanced_models.verifier.provider)}
                      disabled={refreshingModels === draftSettings.ai_endpoints.advanced_models.verifier.provider}
                      className="h-6 w-6 p-0"
                    >
                      {refreshingModels === draftSettings.ai_endpoints.advanced_models.verifier.provider ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3" />
                      )}
                    </Button>
                  </Label>
                  <Combobox
                    value={draftSettings.ai_endpoints.advanced_models.verifier.model_name}
                    onValueChange={(value) => handleAdvancedModelChange('verifier', 'model_name', value)}
                    options={getModelsForModelType('verifier')}
                    placeholder={t('aiSettings.selectModel')}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.apiKey')}</Label>
                  <Input
                    type={editingApiKey['verifier-api-key'] ? 'text' : 'password'}
                    value={editingApiKey['verifier-api-key'] ? 
                      (draftSettings.ai_endpoints.advanced_models.verifier.api_key || '') : 
                      formatApiKeyDisplay(draftSettings.ai_endpoints.advanced_models.verifier.api_key)
                    }
                    onChange={(e) => handleAdvancedModelChange('verifier', 'api_key', e.target.value)}
                    onFocus={() => handleApiKeyFocus('verifier-api-key')}
                    onBlur={() => handleApiKeyBlur('verifier-api-key')}
                    placeholder={t('aiSettings.apiKeyOptional')}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('aiSettings.baseUrl')}</Label>
                  <Input
                    value={draftSettings.ai_endpoints.advanced_models.verifier.base_url}
                    onChange={(e) => handleAdvancedModelChange('verifier', 'base_url', e.target.value)}
                    placeholder={t('aiSettings.baseUrl')}
                    className="h-8 text-sm"
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
