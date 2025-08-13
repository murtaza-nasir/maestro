import { create } from 'zustand'
import { settingsApi } from './settingsApi'

interface ProviderConfig {
  enabled: boolean
  api_key: string | null
  base_url: string | null
}

interface AdvancedModelConfig {
  provider: string
  api_key: string | null
  base_url: string
  model_name: string
}

interface AISettings {
  advanced_mode?: boolean
  providers: {
    openrouter: ProviderConfig
    openai: ProviderConfig
    custom: ProviderConfig
  }
  // Remove the simple models dict - we'll always use advanced_models internally
  advanced_models: {
    fast: AdvancedModelConfig
    mid: AdvancedModelConfig
    intelligent: AdvancedModelConfig
    verifier: AdvancedModelConfig
  }
}

interface SearchSettings {
  provider: 'tavily' | 'linkup' | 'searxng'
  tavily_api_key: string | null
  linkup_api_key: string | null
  searxng_base_url: string | null
  searxng_categories: string | null
  max_results?: number
  search_depth?: 'standard' | 'advanced'
}

export interface ResearchParameters {
  initial_research_max_depth: number
  initial_research_max_questions: number
  structured_research_rounds: number
  writing_passes: number
  thought_pad_context_limit: number
  initial_exploration_doc_results: number
  initial_exploration_web_results: number
  main_research_doc_results: number
  main_research_web_results: number
  max_notes_for_assignment_reranking: number
  max_concurrent_requests: number
  skip_final_replanning: boolean
  auto_optimize_params: boolean
  // Advanced parameters (newly exposed)
  max_research_cycles_per_section?: number
  max_total_iterations?: number
  max_total_depth?: number
  min_notes_per_section_assignment?: number
  max_notes_per_section_assignment?: number
  max_planning_context_chars?: number
  writing_previous_content_preview_chars?: number
  research_note_content_limit?: number
  // Writing mode search parameters
  writing_search_max_iterations?: number
  writing_search_max_queries?: number
  writing_deep_search_iterations?: number
  writing_deep_search_queries?: number
}

interface AppearanceSettings {
  theme: 'light' | 'dark'
  color_scheme: 'default' | 'blue' | 'emerald' | 'purple' | 'rose' | 'amber' | 'teal'
}

interface UserSettings {
  ai_endpoints: AISettings
  search: SearchSettings
  research_parameters: ResearchParameters
  appearance: AppearanceSettings
}

export interface UserProfile {
  full_name: string | null
  location: string | null
  job_title: string | null
}

interface SettingsState {
  settings: UserSettings | null
  draftSettings: UserSettings | null
  profile: UserProfile | null
  draftProfile: UserProfile | null
  isLoading: boolean
  error: string | null
  modelsByProvider: Record<string, string[]>
  isTestingConnection: boolean
  connectionTestResult: { success: boolean; message: string } | null
  modelsFetchError: string | null
  
  // Actions
  loadSettings: () => Promise<void>
  updateSettings: () => Promise<void>
  setDraftSettings: (settings: Partial<UserSettings>) => void
  setProfileField: (field: keyof UserProfile, value: string) => void
  discardDraftChanges: () => void
  testConnection: (provider: string, apiKey: string, baseUrl?: string) => Promise<void>
  fetchAvailableModels: (provider?: string) => Promise<void>
  resetConnectionTest: () => void
  clearModels: () => void
  clearModelsFetchError: () => void
}

// Validation function for AI settings
const validateAISettings = (settings: UserSettings): string | null => {
  const { ai_endpoints } = settings
  
  if (!ai_endpoints.advanced_mode) {
    // Simple mode validation - check enabled provider
    const enabledProvider = Object.entries(ai_endpoints.providers).find(
      ([_, config]) => config.enabled
    )
    
    if (!enabledProvider) {
      return 'Please select an AI provider'
    }
    
    const [providerName, providerConfig] = enabledProvider
    
    // Check if API key is provided for providers that require it
    if ((providerName === 'openrouter' || providerName === 'openai') && !providerConfig.api_key) {
      return `Please provide an API key for ${providerName === 'openrouter' ? 'OpenRouter' : 'OpenAI'}`
    }
    
    // Check if base URL is provided for custom provider
    if (providerName === 'custom' && !providerConfig.base_url) {
      return 'Please provide a base URL for the custom provider'
    }
    
    // Check if all models have names selected
    const modelTypes = ['fast', 'mid', 'intelligent', 'verifier'] as const
    for (const modelType of modelTypes) {
      const model = ai_endpoints.advanced_models[modelType]
      if (!model.model_name) {
        return `Please select a model for ${modelType} configuration`
      }
    }
  } else {
    // Advanced mode validation - check each model individually
    const modelTypes = ['fast', 'mid', 'intelligent', 'verifier'] as const
    for (const modelType of modelTypes) {
      const model = ai_endpoints.advanced_models[modelType]
      
      if (!model.provider) {
        return `Please select a provider for ${modelType} model`
      }
      
      if (!model.model_name) {
        return `Please select a model for ${modelType} configuration`
      }
      
      // Check API key for providers that require it
      if ((model.provider === 'openrouter' || model.provider === 'openai') && !model.api_key) {
        return `Please provide an API key for ${modelType} model (${model.provider})`
      }
      
      // Check base URL for custom provider
      if (model.provider === 'custom' && !model.base_url) {
        return `Please provide a base URL for ${modelType} model (custom provider)`
      }
    }
  }
  
  return null
}

const defaultSettings: UserSettings = {
  appearance: {
    theme: 'light',
    color_scheme: 'default'
  },
  ai_endpoints: {
    advanced_mode: false,
    providers: {
      openrouter: {
        enabled: true,
        api_key: null,
        base_url: 'https://openrouter.ai/api/v1/'
      },
      openai: {
        enabled: false,
        api_key: null,
        base_url: 'https://api.openai.com/v1/'
      },
      custom: {
        enabled: false,
        api_key: null,
        base_url: null
      }
    },
    advanced_models: {
      fast: {
        provider: '',
        api_key: null,
        base_url: '',
        model_name: ''
      },
      mid: {
        provider: '',
        api_key: null,
        base_url: '',
        model_name: ''
      },
      intelligent: {
        provider: '',
        api_key: null,
        base_url: '',
        model_name: ''
      },
      verifier: {
        provider: '',
        api_key: null,
        base_url: '',
        model_name: ''
      }
    }
  },
  search: {
    provider: 'linkup',
    tavily_api_key: null,
    linkup_api_key: null,
    searxng_base_url: null,
    searxng_categories: null,
    max_results: 5,
    search_depth: 'standard'
  },
  research_parameters: {
    initial_research_max_depth: 2,
    initial_research_max_questions: 10,
    structured_research_rounds: 2,
    writing_passes: 3,
    thought_pad_context_limit: 10,
    initial_exploration_doc_results: 5,
    initial_exploration_web_results: 3,
    main_research_doc_results: 5,
    main_research_web_results: 5,
    max_notes_for_assignment_reranking: 80,
    max_concurrent_requests: 5,
    skip_final_replanning: true,
    auto_optimize_params: false
  }
}

export const useSettingsStore = create<SettingsState>()((set, get) => ({
  settings: null,
  draftSettings: null,
  profile: null,
  draftProfile: null,
  isLoading: false,
  error: null,
  modelsByProvider: {},
  isTestingConnection: false,
  connectionTestResult: null,
  modelsFetchError: null,

  loadSettings: async () => {
    try {
      set({ isLoading: true, error: null })
      const [userSettings, userProfile] = await Promise.all([
        settingsApi.getSettings(),
        settingsApi.getProfile()
      ])
      
      // Merge with default settings to ensure all fields are present
      const mergedSettings = {
        ...defaultSettings,
        ...userSettings,
        ai_endpoints: {
          ...defaultSettings.ai_endpoints,
          ...userSettings?.ai_endpoints,
          providers: {
            ...defaultSettings.ai_endpoints.providers,
            ...userSettings?.ai_endpoints?.providers
          },
        },
        search: {
          ...defaultSettings.search,
          ...userSettings?.search
        },
        research_parameters: {
          ...defaultSettings.research_parameters,
          ...userSettings?.research_parameters
        },
        appearance: {
          ...defaultSettings.appearance,
          ...userSettings?.appearance
        }
      }
      
      set({ 
        settings: mergedSettings, 
        draftSettings: mergedSettings, 
        profile: userProfile,
        draftProfile: userProfile,
        isLoading: false 
      })
    } catch (error) {
      console.error('Failed to load settings:', error)
      set({ 
        error: 'Failed to load settings', 
        isLoading: false,
        settings: defaultSettings,
        draftSettings: defaultSettings,
        profile: null,
        draftProfile: null
      })
    }
  },

  setDraftSettings: (newDraftSettings) => {
    set(state => {
      if (!state.draftSettings) return state;
      
      // If the newDraftSettings is a complete settings object (has all required properties),
      // use it directly instead of merging
      if (newDraftSettings.ai_endpoints && newDraftSettings.search && 
          newDraftSettings.research_parameters && newDraftSettings.appearance) {
        return {
          draftSettings: newDraftSettings as UserSettings
        };
      }
      
      // Otherwise, do the deep merge for partial updates
      return {
        draftSettings: {
          ...state.draftSettings,
          ...newDraftSettings,
          ai_endpoints: newDraftSettings.ai_endpoints ? {
            ...state.draftSettings.ai_endpoints,
            ...newDraftSettings.ai_endpoints,
            providers: newDraftSettings.ai_endpoints.providers ? {
              ...state.draftSettings.ai_endpoints.providers,
              ...newDraftSettings.ai_endpoints.providers
            } : state.draftSettings.ai_endpoints.providers,
            advanced_models: newDraftSettings.ai_endpoints.advanced_models ? {
              ...state.draftSettings.ai_endpoints.advanced_models,
              ...newDraftSettings.ai_endpoints.advanced_models
            } : state.draftSettings.ai_endpoints.advanced_models
          } : state.draftSettings.ai_endpoints,
          search: newDraftSettings.search ? {
            ...state.draftSettings.search,
            ...newDraftSettings.search
          } : state.draftSettings.search,
          research_parameters: newDraftSettings.research_parameters ? {
            ...state.draftSettings.research_parameters,
            ...newDraftSettings.research_parameters
          } : state.draftSettings.research_parameters,
          appearance: newDraftSettings.appearance ? {
            ...state.draftSettings.appearance,
            ...newDraftSettings.appearance
          } : state.draftSettings.appearance
        }
      };
    })
  },

  setProfileField: (field, value) => {
    set(state => {
      if (!state.draftProfile) return state;
      
      return {
        draftProfile: {
          ...state.draftProfile,
          [field]: value
        }
      };
    })
  },

  discardDraftChanges: () => {
    set(state => ({ 
      draftSettings: state.settings,
      draftProfile: state.profile 
    }))
  },

  updateSettings: async () => {
    const { draftSettings, draftProfile } = get()
    if (!draftSettings || !draftProfile) return

    try {
      set({ isLoading: true, error: null })
      
      // Validate AI settings before saving
      const validationError = validateAISettings(draftSettings)
      if (validationError) {
        set({ 
          error: validationError, 
          isLoading: false 
        })
        throw new Error(validationError)
      }
      
      const [savedSettings, savedProfile] = await Promise.all([
        settingsApi.updateSettings(draftSettings),
        settingsApi.updateProfile(draftProfile)
      ])
      
      set({ 
        settings: savedSettings, 
        draftSettings: savedSettings, 
        profile: savedProfile,
        draftProfile: savedProfile,
        isLoading: false 
      })
    } catch (error: any) {
      console.error('Failed to update settings:', error)
      const errorMessage = error.response?.data?.detail || 
                          error.message || 
                          'Failed to update settings'
      set({ 
        error: errorMessage, 
        isLoading: false 
      })
      throw error
    }
  },

  testConnection: async (provider, apiKey, baseUrl) => {
    try {
      set({ isTestingConnection: true, connectionTestResult: null, error: null })
      
      const result = await settingsApi.testConnection(provider, apiKey, baseUrl)
      
      set({ 
        isTestingConnection: false, 
        connectionTestResult: result 
      })
    } catch (error: any) {
      console.error('Connection test failed:', error)
      set({ 
        isTestingConnection: false, 
        connectionTestResult: { 
          success: false, 
          message: error.response?.data?.detail || 'Connection test failed' 
        }
      })
    }
  },

  fetchAvailableModels: async (provider?: string) => {
    try {
      set({ isLoading: true, modelsFetchError: null })
      const { draftSettings } = get()
      let apiKey: string | undefined
      let baseUrl: string | undefined
      
      if (draftSettings && provider) {
        // In simple mode, get from the enabled provider
        if (!draftSettings.ai_endpoints.advanced_mode) {
          const providerConfig = draftSettings.ai_endpoints.providers[provider as keyof typeof draftSettings.ai_endpoints.providers]
          if (providerConfig) {
            apiKey = providerConfig.api_key || undefined
            baseUrl = providerConfig.base_url || undefined
          }
        } else {
          // In advanced mode, get from any model using this provider
          const advancedModels = draftSettings.ai_endpoints.advanced_models
          for (const modelConfig of Object.values(advancedModels)) {
            if (modelConfig.provider === provider && modelConfig.api_key) {
              apiKey = modelConfig.api_key
              baseUrl = modelConfig.base_url
              break
            }
          }
        }
      }
      
      const modelsResult = await settingsApi.getAvailableModels(provider, apiKey, baseUrl)
      set(state => ({ 
        modelsByProvider: {
          ...state.modelsByProvider,
          [provider || 'default']: modelsResult.models || []
        },
        isLoading: false,
        modelsFetchError: null
      }))
    } catch (error: any) {
      console.error('Failed to fetch models:', error)
      const errorMessage = error.response?.data?.detail || 
                          error.message || 
                          'Failed to fetch models. Please check your API key and base URL.'
      set({ 
        modelsFetchError: errorMessage,
        isLoading: false
      })
    }
  },

  resetConnectionTest: () => {
    set({ connectionTestResult: null })
  },

  clearModels: () => {
    set({ modelsByProvider: {}, modelsFetchError: null })
  },

  clearModelsFetchError: () => {
    set({ modelsFetchError: null })
  }
}))
