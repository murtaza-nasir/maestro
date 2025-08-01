import logging
from typing import Optional
from sqlalchemy.orm import Session

from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.config import get_model_name, AGENT_ROLE_TEMPERATURE
from database import crud
from database.models import Chat

logger = logging.getLogger(__name__)

class ChatTitleService:
    """
    Service for generating intelligent chat titles using the lightweight model.
    Generates concise, research-focused titles after the first AI response.
    """
    
    def __init__(self, model_dispatcher: ModelDispatcher):
        self.model_dispatcher = model_dispatcher
        
    def _get_title_generation_prompt(self, user_message: str, ai_response: str) -> str:
        """
        Generate a context-appropriate prompt for title generation.
        Detects if this is a writing or research conversation and adjusts accordingly.
        """
        # Simple heuristic to detect writing vs research context
        writing_keywords = ["write", "writing", "draft", "document", "edit", "revise", "content", "article", "essay", "paper", "section", "paragraph"]
        research_keywords = ["research", "find", "search", "analyze", "study", "investigate", "explore", "compare"]
        
        combined_text = (user_message + " " + ai_response).lower()
        
        writing_score = sum(1 for keyword in writing_keywords if keyword in combined_text)
        research_score = sum(1 for keyword in research_keywords if keyword in combined_text)
        
        is_writing_context = writing_score > research_score
        
        if is_writing_context:
            return f"""You are a title generator for MAESTRO, an AI-powered writing assistant that helps users create and improve documents.

Your task is to create a concise, descriptive title (3-6 words) that captures the essence of this writing conversation. The title should reflect the writing topic, document type, or content being worked on.

Consider these writing contexts:
- Document creation and editing
- Content generation and improvement
- Academic writing and papers
- Business documents and reports
- Creative writing projects
- Technical documentation
- Article and blog writing

CONVERSATION:
User: {user_message}

AI Writing Assistant: {ai_response}

Generate a clear, professional title that would help users quickly identify this writing conversation in their chat history. Focus on the main writing topic or document being worked on.

Examples of good writing titles:
- "Business Plan Draft"
- "Research Paper Introduction"
- "Marketing Content Creation"
- "Technical Documentation"
- "Essay Revision Help"

Title:"""
        else:
            return f"""You are a title generator for MAESTRO, an AI-powered research assistant that uses multiple specialized agents to conduct comprehensive research.

Your task is to create a concise, descriptive title (3-6 words) that captures the essence of this research conversation. The title should reflect the research topic, question type, or domain being explored.

Consider these research contexts:
- Academic research and literature reviews
- Market research and analysis
- Technical investigations
- Data analysis and insights
- Comparative studies
- Trend analysis
- Problem-solving research

CONVERSATION:
User: {user_message}

AI Research Assistant: {ai_response}

Generate a clear, professional title that would help users quickly identify this research conversation in their chat history. Focus on the main research topic or question being explored.

Examples of good research titles:
- "AI Ethics Literature Review"
- "Climate Change Data Analysis"
- "Market Trends in Fintech"
- "Python Performance Optimization"
- "Healthcare AI Applications"

Title:"""

    async def generate_title(self, user_message: str, ai_response: str) -> str:
        """
        Generate a title using the fast/lightweight model.
        
        Args:
            user_message: The user's initial message
            ai_response: The AI's first response
            
        Returns:
            Generated title string, or fallback if generation fails
        """
        try:
            # Get the lightweight model configuration
            model_name = get_model_name("fast")
            temperature = AGENT_ROLE_TEMPERATURE.get("messenger", 0.3)  # Use messenger temp or fallback
            
            # Generate the prompt
            prompt = self._get_title_generation_prompt(user_message, ai_response)
            
            # Call the model dispatcher
            response, model_details = await self.model_dispatcher.dispatch(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,  # Use the specific model name
                agent_mode="messenger"  # Use messenger mode for chat-like interactions
            )
            
            if response and response.choices and response.choices[0].message and response.choices[0].message.content:
                title = response.choices[0].message.content.strip()
                
                # Clean up the title
                title = title.replace('"', '').replace("'", "")
                if title.startswith("Title:"):
                    title = title[6:].strip()
                
                # Ensure reasonable length
                if len(title) > 60:
                    title = title[:57] + "..."
                
                # Fallback if title is too short or empty
                if len(title) < 3:
                    return self._generate_fallback_title(user_message)
                
                logger.info(f"Generated chat title: '{title}'")
                return title
            else:
                logger.warning("Empty response from model dispatcher for title generation")
                return self._generate_fallback_title(user_message)
                
        except Exception as e:
            # For chat title generation, we don't want to show the full error message to users
            # since this is a background operation, but we'll log the proper error handling
            from ai_researcher.agentic_layer.utils.error_messages import handle_api_error
            
            logger.error(f"Error generating chat title: {e}", exc_info=True)
            error_message = handle_api_error(e)
            logger.info(f"Chat title generation failed with user-friendly error: {error_message}")
            return self._generate_fallback_title(user_message)
    
    def _generate_fallback_title(self, user_message: str) -> str:
        """
        Generate a fallback title when AI generation fails.
        """
        # Simple rule-based fallback
        title = user_message.strip()
        
        # Truncate if too long
        if len(title) > 50:
            title = title[:47] + "..."
        
        return title
    
    def should_update_title(self, chat: Chat) -> bool:
        """
        Determine if the chat title should be updated.
        
        Args:
            chat: The chat object to check
            
        Returns:
            True if title should be updated, False otherwise
        """
        if not chat or not chat.title:
            logger.debug(f"Chat {chat.id if chat else 'None'} has no title, allowing update.")
            return True

        # Find the first user message to compare against the title
        first_user_message = next((m.content.strip() for m in chat.messages if m.role == "user"), None)

        if not first_user_message:
            logger.debug(f"Chat {chat.id} has no user messages, skipping title update for now.")
            return False

        current_title = chat.title.strip()
        logger.debug(f"Chat {chat.id} title check: current='{current_title}', first_user='{first_user_message}'")

        # If title is the same as the start of the first message, it's a temporary title and should be updated.
        if first_user_message.startswith(current_title.replace("...", "")):
             logger.debug(f"Chat {chat.id} title is temporary, should update.")
             return True

        # If title is a generic placeholder, it should be updated.
        generic_titles = [
            "new chat", "chat", "conversation", "untitled",
            "new writing chat", "writing chat", "new research chat", "research chat"
        ]
        if current_title.lower() in generic_titles:
            logger.debug(f"Chat {chat.id} title is generic, should update.")
            return True
        
        logger.debug(f"Chat {chat.id} title does not need updating")
        return False
    
    async def update_title_if_needed(self, db: Session, chat_id: str, user_id: int, user_message: str, ai_response: str) -> bool:
        """
        Generate and update chat title after the first AI response, only if necessary.
        
        Args:
            db: Database session
            chat_id: ID of the chat to update
            user_id: ID of the user (for security)
            user_message: The user's first message
            ai_response: The AI's first response
            
        Returns:
            True if title was updated, False otherwise
        """
        try:
            # First, get the current chat from the database
            current_chat = crud.get_chat(db, chat_id, user_id)
            if not current_chat:
                logger.warning(f"Chat {chat_id} not found for user {user_id}, cannot update title.")
                return False

            # Decide if the title needs to be updated
            if not self.should_update_title(current_chat):
                logger.debug(f"Skipping title update for chat {chat_id} as it's not needed.")
                return False

            # Generate the new title using the provided messages
            new_title = await self.generate_title(user_message, ai_response)
            
            # Update the title in the database
            updated_chat = crud.update_chat_title(db, chat_id, user_id, new_title)
            
            if updated_chat:
                logger.info(f"Updated chat {chat_id} title to: '{new_title}'")
                return True
            else:
                logger.error(f"Failed to update chat {chat_id} title in database")
                return False
                
        except Exception as e:
            logger.error(f"Error updating chat title for {chat_id}: {e}", exc_info=True)
            return False
