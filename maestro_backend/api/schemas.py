from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from ai_researcher.agentic_layer.schemas.goal import GoalEntry
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserProfile(BaseModel):
    full_name: Optional[str] = None
    location: Optional[str] = None
    job_title: Optional[str] = None

class UserProfileUpdate(UserProfile):
    pass

class User(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    settings: Optional[Dict[str, Any]] = None
    profile: Optional[UserProfile] = None
    is_admin: bool
    is_active: bool
    role: str
    user_type: str

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class UserUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None
    user_type: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    profile: Optional[UserProfileUpdate] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

class AppearanceSettings(BaseModel):
    theme: Optional[str] = 'light'
    color_scheme: Optional[str] = 'default'

class ProviderConfig(BaseModel):
    enabled: bool
    api_key: Optional[str] = None
    base_url: Optional[str] = None

class AdvancedModelConfig(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None

class AISettings(BaseModel):
    advanced_mode: Optional[bool] = False
    providers: Dict[str, ProviderConfig]
    # Remove the simple models dict - we'll always use advanced_models internally
    advanced_models: Dict[str, AdvancedModelConfig]

class SearchSettings(BaseModel):
    provider: str
    tavily_api_key: Optional[str] = None
    linkup_api_key: Optional[str] = None
    searxng_base_url: Optional[str] = None
    searxng_categories: Optional[str] = None

class ResearchParameters(BaseModel):
    initial_research_max_depth: int
    initial_research_max_questions: int
    structured_research_rounds: int
    writing_passes: int
    thought_pad_context_limit: int
    initial_exploration_doc_results: int
    initial_exploration_web_results: int
    main_research_doc_results: int
    main_research_web_results: int
    max_notes_for_assignment_reranking: int
    max_concurrent_requests: int
    skip_final_replanning: bool
    auto_optimize_params: bool

class GlobalUserSettings(BaseModel):
    ai_endpoints: Optional[AISettings] = None
    search: Optional[SearchSettings] = None
    research_parameters: Optional[ResearchParameters] = None
    appearance: Optional[AppearanceSettings] = None
    writing_settings: Optional[Dict[str, Any]] = None  # For writing-specific settings like custom system prompt

# Chat-related schemas
class MessageBase(BaseModel):
    content: str
    role: str  # 'user' or 'assistant'

class MessageCreate(MessageBase):
    pass

class Message(MessageBase):
    id: str
    chat_id: str
    sources: Optional[List[Dict[str, Any]]] = None  # Sources for assistant messages
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ChatBase(BaseModel):
    title: str

class ChatCreate(ChatBase):
    chat_type: Optional[str] = "research"  # Default to research for backward compatibility

class ChatUpdate(BaseModel):
    title: Optional[str] = None

class Chat(ChatBase):
    id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    messages: List[Message] = []
    missions: List["Mission"] = []

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ChatSummary(ChatBase):
    """Chat without messages and missions for list views."""
    id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = None
    active_mission_count: Optional[int] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# Mission-related schemas
class MissionBase(BaseModel):
    user_request: str

class MissionUpdate(BaseModel):
    status: Optional[str] = None
    error_info: Optional[str] = None
    mission_context: Optional[Dict[str, Any]] = None

class Mission(MissionBase):
    id: str
    chat_id: str
    status: str
    mission_context: Optional[Dict[str, Any]] = None
    error_info: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class MissionResponse(BaseModel):
    mission_id: str
    status: str
    created_at: datetime
    user_request: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class MissionStatus(BaseModel):
    mission_id: str
    status: str
    updated_at: datetime
    error_info: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class MissionStats(BaseModel):
    mission_id: str
    total_cost: float
    total_prompt_tokens: float
    total_completion_tokens: float
    total_native_tokens: float
    total_web_search_calls: int

class MissionPlan(BaseModel):
    mission_id: str
    plan: Optional[Dict[str, Any]] = None

class MissionReport(BaseModel):
    mission_id: str
    final_report: Optional[str] = None

class MissionLog(BaseModel):
    timestamp: datetime
    agent_name: str
    message: str
    # Rich metadata fields from database
    action: Optional[str] = None
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    full_input: Optional[Any] = None  # Can be string or dict
    full_output: Optional[Any] = None  # Can be string or dict
    model_details: Optional[Dict[str, Any]] = None
    tool_calls: Optional[Any] = None  # Can be list or dict
    file_interactions: Optional[Any] = None  # Can be list or dict
    cost: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    native_tokens: Optional[int] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class MissionLogs(BaseModel):
    mission_id: str
    logs: List[MissionLog]

class MissionDraft(BaseModel):
    mission_id: str
    draft: Optional[str] = None

class MissionContextResponse(BaseModel):
    mission_id: str
    goal_pad: List[GoalEntry]
    thought_pad: List[ThoughtEntry]
    agent_scratchpad: Optional[str] = None

# Mission Settings Schema
class MissionSettings(BaseModel):
    """Research parameters that can be customized per mission."""
    # Initial Research Parameters
    initial_research_max_depth: Optional[int] = Field(None, description="Max depth for initial question tree")
    initial_research_max_questions: Optional[int] = Field(None, description="Max total questions in initial phase")
    
    # Structured Research Parameters
    structured_research_rounds: Optional[int] = Field(None, description="Number of structured research rounds")
    writing_passes: Optional[int] = Field(None, description="Number of writing passes (initial + revisions)")
    
    # Search Results Configuration
    initial_exploration_doc_results: Optional[int] = Field(None, description="Number of docs for initial exploration")
    initial_exploration_web_results: Optional[int] = Field(None, description="Number of web results for initial exploration")
    main_research_doc_results: Optional[int] = Field(None, description="Number of docs for main research cycles")
    main_research_web_results: Optional[int] = Field(None, description="Number of web results for main research cycles")
    
    # Thought Management
    thought_pad_context_limit: Optional[int] = Field(None, description="Number of recent thoughts to provide as context")
    
    # Performance Settings
    max_notes_for_assignment_reranking: Optional[int] = Field(None, description="Max notes to pass to NoteAssignmentAgent after reranking")
    max_concurrent_requests: Optional[int] = Field(None, description="Max concurrent requests for agent operations")
    
    # Options
    skip_final_replanning: Optional[bool] = Field(None, description="Toggle to skip final outline refinement")
    auto_optimize_params: Optional[bool] = Field(None, description="Enable AI to dynamically optimize research params")

class MissionSettingsResponse(BaseModel):
    mission_id: str
    settings: Optional[MissionSettings] = None
    effective_settings: MissionSettings  # The actual settings being used (after fallback)

class MissionSettingsUpdate(BaseModel):
    settings: MissionSettings

class SystemStatus(BaseModel):
    status: str
    version: str
    components: Dict[str, str]
    uptime: str

# Document and DocumentGroup Schemas

from pydantic import BaseModel, Field

class DocumentBase(BaseModel):
    original_filename: str
    metadata_: Optional[Dict[str, Any]] = None

class DocumentCreate(DocumentBase):
    id: str

class Document(DocumentBase):
    id: str
    user_id: int
    created_at: Optional[datetime] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    processing_status: Optional[str] = None
    upload_progress: Optional[int] = None
    file_size: Optional[int] = None
    processing_error: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class DocumentGroupBase(BaseModel):
    name: str
    description: Optional[str] = None

class DocumentGroupCreate(DocumentGroupBase):
    pass

class DocumentGroupUpdate(DocumentGroupBase):
    pass

class DocumentGroup(DocumentGroupBase):
    id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    documents: List[Document] = []

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class DocumentGroupWithCount(DocumentGroupBase):
    id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    documents: List[Document] = []
    document_count: int

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class DocumentProgressUpdate(BaseModel):
    user_id: int
    doc_id: str
    progress: int
    status: str
    error: Optional[str] = None
    timestamp: str

# Pagination schemas
class PaginationInfo(BaseModel):
    total_count: int
    page: int
    limit: int
    total_pages: int
    has_next: bool
    has_previous: bool

class PaginatedDocumentResponse(BaseModel):
    documents: List[Document]
    pagination: PaginationInfo
    filters_applied: Dict[str, Any]

class DocumentFilters(BaseModel):
    search: Optional[str] = None
    author: Optional[str] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    status: Optional[str] = None
    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: Optional[str] = Field("desc", description="Sort order: asc or desc")

# Writing View Schemas

class WritingSessionBase(BaseModel):
    document_group_id: Optional[str] = None
    use_web_search: bool = True
    settings: Optional[Dict[str, Any]] = None

class WritingSessionCreate(WritingSessionBase):
    chat_id: str

class WritingSessionUpdate(BaseModel):
    document_group_id: Optional[str] = None
    use_web_search: Optional[bool] = None
    current_draft_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

class WritingSession(WritingSessionBase):
    id: str
    chat_id: str
    current_draft_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class DraftBase(BaseModel):
    title: str
    content: str  # Markdown text content
    version: int = 1

class DraftCreate(DraftBase):
    writing_session_id: str

class DraftUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_current: Optional[bool] = None

class Draft(DraftBase):
    id: str
    writing_session_id: str
    is_current: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ReferenceBase(BaseModel):
    document_id: Optional[str] = None
    web_url: Optional[str] = None
    citation_text: str
    context: Optional[str] = None
    reference_type: str  # 'document' or 'web'

class ReferenceCreate(ReferenceBase):
    draft_id: str

class Reference(ReferenceBase):
    id: str
    draft_id: str
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class WritingSessionWithChat(BaseModel):
    id: str
    name: str  # Chat title
    chat_id: str
    document_group_id: Optional[str] = None
    document_group_name: Optional[str] = None
    web_search_enabled: bool = True
    current_draft_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class WritingSessionWithDrafts(WritingSession):
    drafts: List[Draft] = []
    current_draft: Optional[Draft] = None

class DraftWithReferences(Draft):
    references: List[Reference] = []

class ReferenceCreate(BaseModel):
    reference_type: str  # "document" or "web"
    citation_text: str
    document_id: Optional[str] = None  # For document references
    web_url: Optional[str] = None  # For web references
    context: Optional[Dict[str, Any]] = None

# Writing Chat Schemas

class WritingChatRequest(BaseModel):
    draft_id: str
    message: str

class WritingSuggestionRequest(BaseModel):
    draft_id: str

class CitationRecommendationRequest(BaseModel):
    draft_id: str
    content: str

# Enhanced Writing Agent Schemas

class WritingOperation(BaseModel):
    type: str  # 'rag_search', 'document_operation', 'content_generation', 'tool_call'
    operation: Optional[str] = None  # Specific operation name
    query: Optional[str] = None
    target_element_id: Optional[str] = None
    content: Optional[str] = None
    references: Optional[List[str]] = None
    revision_step: Optional[int] = None
    context: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

class ContextUsage(BaseModel):
    document_outline: bool = False
    full_document: bool = False
    references: bool = False
    search_results: bool = False
    conversation_history: bool = False
    document_group: bool = False

class RevisionStepsExecuted(BaseModel):
    rag_search: int = 0
    content_generation: int = 0
    tool_calls: int = 0
    citation_search: int = 0

class OperationProgress(BaseModel):
    operation_type: str  # 'rag_search', 'content_generation', 'tool_call'
    current_step: int
    total_steps: int
    status: str  # 'running', 'completed', 'error'
    description: str

# Source schemas for writing responses
class SourceBase(BaseModel):
    type: str  # 'web' or 'document'
    title: str

class WebSource(SourceBase):
    type: str = 'web'
    url: str
    provider: Optional[str] = None

class DocumentSource(SourceBase):
    type: str = 'document'
    page: str
    doc_id: str
    chunk_id: str

class WritingAgentResponse(BaseModel):
    message: str
    sources: List[Dict[str, Any]] = []  # List of source objects (web or document)
    operations: List[WritingOperation] = []
    context_used: ContextUsage
    revision_steps_executed: RevisionStepsExecuted
    settings_applied: Optional[Dict[str, Any]] = None
    operation_progress: Optional[List[OperationProgress]] = None
    error: Optional[str] = None
    updated_title: Optional[str] = None  # Updated chat title if it was changed

class WritingSessionSettings(BaseModel):
    model_selection: Optional[Dict[str, str]] = None  # {"endpoint": "openai_gpt4", "model": "gpt-4-turbo"}
    revision_settings: Optional[Dict[str, int]] = None  # {"rag_search_revisions": 2, "content_generation_revisions": 1, ...}
    context_settings: Optional[Dict[str, Any]] = None  # {"always_include_outline": True, "include_full_document_threshold": 5000, ...}
    operation_settings: Optional[Dict[str, Any]] = None  # {"auto_save_drafts": True, "confirm_major_changes": False, ...}
    custom_system_prompt: Optional[str] = None  # Custom system prompt for the writing agent

class EnhancedWritingChatRequest(BaseModel):
    draft_id: str
    message: str
    session_settings: Optional[WritingSessionSettings] = None
    context_override: Optional[Dict[str, Any]] = None  # Override default context inclusion
    operation_mode: Optional[str] = None  # 'research_heavy', 'writing_focused', 'balanced'
    document_group_id: Optional[str] = None
    use_web_search: Optional[bool] = None

class WritingSessionSettingsUpdate(BaseModel):
    settings: WritingSessionSettings

class WritingSessionStats(BaseModel):
    session_id: str
    total_cost: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_native_tokens: int
    total_web_searches: int
    total_document_searches: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class WritingSessionStatsUpdate(BaseModel):
    cost_delta: Optional[float] = 0.0
    prompt_tokens_delta: Optional[int] = 0
    completion_tokens_delta: Optional[int] = 0
    native_tokens_delta: Optional[int] = 0
    web_searches_delta: Optional[int] = 0
    document_searches_delta: Optional[int] = 0

# Dashboard Stats Schema
class DashboardStats(BaseModel):
    total_chats: int
    total_documents: int
    total_writing_sessions: int
    total_missions: int
    recent_activity: Optional[str] = None
    research_sessions: int  # Chats with type 'research'
    writing_sessions: int   # Actual writing sessions count
    completed_missions: int
    active_missions: int

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# System Settings Schemas
class SystemSettingsResponse(BaseModel):
    registration_enabled: bool
    max_users_allowed: int
    instance_name: str

class SystemSettingsUpdate(BaseModel):
    registration_enabled: Optional[bool] = None
    max_users_allowed: Optional[int] = None
    instance_name: Optional[str] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str
