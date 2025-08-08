from typing import Optional, List, Literal, ClassVar
from pydantic import BaseModel, Field, ConfigDict

# Define the possible intents for the messenger agent
IntentType = Literal["start_research", "refine_questions", "refine_goal", "approve_questions", "chat"] # Added refine_goal

class MessengerResponse(BaseModel):
    """
    Schema for the response from the MessengerAgent.
    This is the structured output that the agent returns after processing a user message.
    """
    intent: IntentType = Field(
        description="The detected intent of the user's message: 'start_research', 'refine_questions', 'refine_goal', 'approve_questions', or 'chat'" # Added refine_goal
    )
    extracted_content: Optional[str] = Field(
        None,
        description="The extracted research topic or feedback from the user's message, if applicable"
    )
    formatting_preferences: Optional[str] = Field(
        None,
        description="Any detected formatting preferences like tone, length, format, or audience"
    )
    response_to_user: str = Field(
        description="The text response to show to the user"
    )
    thoughts: str = Field(
        description="The agent's analysis and reasoning about the user's message (not shown to user)"
    )
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

class ChatMessage(BaseModel):
    """
    Schema for a chat message in the conversation history.
    """
    role: Literal["user", "assistant"] = Field(
        description="The role of the message sender: 'user' or 'assistant'"
    )
    content: str = Field(
        description="The content of the message"
    )
    timestamp: Optional[str] = Field(
        None,
        description="The timestamp of when the message was sent (optional)"
    )
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

class ChatHistory(BaseModel):
    """
    Schema for the chat history between the user and the assistant.
    """
    messages: List[ChatMessage] = Field(
        default_factory=list,
        description="The list of messages in the conversation"
    )
    mission_id: Optional[str] = Field(
        None,
        description="The ID of the associated research mission, if any"
    )
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')
