import { apiClient, API_CONFIG } from '../../../config/api'

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

export interface AISettings {
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

export interface SearchSettings {
  provider: 'tavily' | 'linkup' | 'searxng'
  tavily_api_key: string | null
  linkup_api_key: string | null
  searxng_base_url: string | null
  searxng_categories: string | null
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
}

export interface AppearanceSettings {
  theme: 'light' | 'dark'
  color_scheme: 'default' | 'blue' | 'emerald' | 'purple' | 'rose' | 'amber' | 'teal'
}

export interface UserSettings {
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

export interface ConnectionTestResult {
  success: boolean
  message: string
}

export interface AvailableModelsResult {
  provider: string
  models: string[]
}

export const settingsApi = {
  // Get user settings
  getSettings: async (): Promise<UserSettings> => {
    const response = await apiClient.get(API_CONFIG.ENDPOINTS.SETTINGS.GET)
    return response.data
  },

  // Update user settings
  updateSettings: async (settings: UserSettings): Promise<UserSettings> => {
    const response = await apiClient.put(API_CONFIG.ENDPOINTS.SETTINGS.UPDATE, { settings })
    return response.data
  },

  // Test AI connection
  testConnection: async (
    provider: string,
    apiKey: string,
    baseUrl?: string
  ): Promise<ConnectionTestResult> => {
    const response = await apiClient.post(API_CONFIG.ENDPOINTS.SETTINGS.TEST_CONNECTION, {
      provider,
      api_key: apiKey,
      base_url: baseUrl
    })
    return response.data
  },

  // Get available models
  getAvailableModels: async (
    provider?: string, 
    apiKey?: string, 
    baseUrl?: string
  ): Promise<AvailableModelsResult> => {
    const params = new URLSearchParams()
    if (provider) params.append('provider', provider)
    if (apiKey) params.append('api_key', apiKey)
    if (baseUrl) params.append('base_url', baseUrl)
    
    const url = params.toString() 
      ? `${API_CONFIG.ENDPOINTS.SETTINGS.GET_MODELS}?${params.toString()}`
      : API_CONFIG.ENDPOINTS.SETTINGS.GET_MODELS
    const response = await apiClient.get(url)
    return response.data
  },

  // Get user profile
  getProfile: async (): Promise<UserProfile> => {
    const response = await apiClient.get(API_CONFIG.ENDPOINTS.PROFILE.GET)
    return response.data
  },

  // Update user profile
  updateProfile: async (profile: UserProfile): Promise<UserProfile> => {
    const response = await apiClient.put(API_CONFIG.ENDPOINTS.PROFILE.UPDATE, profile)
    return response.data
  }
}
