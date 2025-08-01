from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel
import logging
import asyncio
import queue

from auth.dependencies import get_current_user_from_cookie, get_db
from database.models import User
from sqlalchemy.orm import Session
# Import the shared instances from missions API
from api.missions import get_user_specific_agent_controller
from services.chat_title_service import ChatTitleService

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

# Pydantic models for chat API
class ChatMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    message: str
    chat_id: str
    conversation_history: Optional[List[ChatMessage]] = []
    mission_id: Optional[str] = None  # Associate chat with a mission
    document_group_id: Optional[str] = None  # Selected document group for local RAG
    use_web_search: Optional[bool] = True  # Enable/disable web search

class ChatResponse(BaseModel):
    response: str
    action: Optional[str] = None  # MessengerAgent actions: start_research, refine_questions, approve_questions, etc.
    request: Optional[str] = None  # Extracted content for the action
    mission_id: Optional[str] = None  # Mission ID if created or associated
    model_used: Optional[str] = None
    provider: Optional[str] = None
    cost: Optional[float] = None
    updated_title: Optional[str] = None  # Updated chat title if it was changed

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    current_user: User = Depends(get_current_user_from_cookie),
    agent_controller = Depends(get_user_specific_agent_controller),
    db: Session = Depends(get_db)
):
    """
    Chat with the AI using the MessengerAgent and collaborative research flow.
    This integrates with the full agentic system for intent detection and research mission management.
    """
    if not agent_controller:
        logger.error("Agent controller not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI chat service is not available. Please try again later."
        )
    
    try:
        # Convert ChatMessage objects to tuples for the AgentController
        chat_history: List[Tuple[str, str]] = []
        for msg in request.conversation_history:
            if msg.role == "user":
                # Find the next assistant message to pair with this user message
                next_assistant_msg = None
                current_index = request.conversation_history.index(msg)
                for i in range(current_index + 1, len(request.conversation_history)):
                    if request.conversation_history[i].role == "assistant":
                        next_assistant_msg = request.conversation_history[i].content
                        break
                
                if next_assistant_msg:
                    chat_history.append((msg.content, next_assistant_msg))
        
        logger.info(f"Processing chat request from user {current_user.username} with {len(chat_history)} history pairs")
        
        # Create a queue and callback for WebSocket updates if a mission is involved
        log_queue = queue.Queue() if request.mission_id else None
        
        def websocket_update_callback(q: queue.Queue, update_data: Any):
            """Callback to send updates via WebSocket for mission-related activities."""
            try:
                from api.websockets import send_logs_update
                
                if hasattr(update_data, 'agent_name') and hasattr(update_data, 'action'):
                    log_entry_dict = {
                        "timestamp": update_data.timestamp.isoformat(),
                        "agent_name": update_data.agent_name,
                        "action": update_data.action,
                        "input_summary": getattr(update_data, 'input_summary', None),
                        "output_summary": getattr(update_data, 'output_summary', None),
                        "status": getattr(update_data, 'status', 'success'),
                        "error_message": getattr(update_data, 'error_message', None),
                        "full_input": getattr(update_data, 'full_input', None),
                        "full_output": getattr(update_data, 'full_output', None),
                        "model_details": getattr(update_data, 'model_details', None),
                        "tool_calls": getattr(update_data, 'tool_calls', None),
                        "file_interactions": getattr(update_data, 'file_interactions', None)
                    }
                    
                    mission_id_to_log = request.mission_id or agent_result.get("mission_id")
                    if mission_id_to_log:
                        asyncio.create_task(send_logs_update(mission_id_to_log, [log_entry_dict]))

            except Exception as e:
                logger.error(f"Error in chat's websocket_update_callback: {e}")

        # Use the AgentController's handle_user_message method
        try:
            agent_result = await agent_controller.handle_user_message(
                user_message=request.message,
                chat_history=chat_history,
                chat_id=request.chat_id,
                mission_id=request.mission_id,
                log_queue=log_queue,
                update_callback=websocket_update_callback if request.mission_id else None,
                use_web_search=request.use_web_search,
                document_group_id=request.document_group_id
            )
        except Exception as agent_error:
            logger.error(f"AgentController error: {agent_error}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "AI Agent Error",
                    "message": f"AI agent error: {str(agent_error)}",
                    "type": "agent_error",
                    "technical_details": str(agent_error)
                }
            )
        
        if not agent_result:
            logger.error("AgentController returned empty result")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "Empty Agent Response",
                    "message": "Failed to get a valid response from the AI agent. Please try again.",
                    "type": "agent_response_error"
                }
            )
        
        # Extract the response and action information
        response_text = agent_result.get("response", "")
        action = agent_result.get("action")
        request_content = agent_result.get("request")
        mission_id = agent_result.get("mission_id")  # This will be set if a new mission was created
        
        if not response_text or not response_text.strip():
            logger.error("Empty response from AgentController")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "Empty Agent Response",
                    "message": "Received an empty response from the AI agent. Please try again.",
                    "type": "agent_response_error"
                }
            )
        
        logger.info(f"Chat response generated successfully. Action: {action}, Mission ID: {mission_id}")
        
        # Generate intelligent chat title after successful AI response
        updated_title = None
        try:
            logger.info(f"Attempting to generate intelligent title for chat {request.chat_id}")
            title_service = ChatTitleService(agent_controller.model_dispatcher)
            
            title_updated = await title_service.update_title_if_needed(
                db=db,
                chat_id=request.chat_id,
                user_id=current_user.id,
                user_message=request.message,
                ai_response=response_text
            )
            if title_updated:
                logger.info(f"Chat title updated successfully for chat {request.chat_id}")
                # Get the updated title to return to frontend
                from database import crud
                updated_chat = crud.get_chat(db, request.chat_id, current_user.id)
                if updated_chat:
                    updated_title = updated_chat.title
            else:
                logger.info(f"Chat title did not need updating for chat {request.chat_id}")
                
        except Exception as title_error:
            # Don't let title generation errors affect the main chat response
            logger.warning(f"Failed to update chat title for {request.chat_id}: {title_error}", exc_info=True)
        
        return ChatResponse(
            response=response_text.strip(),
            action=action,
            request=request_content,
            mission_id=mission_id or request.mission_id,  # Return new mission_id or existing one
            model_used=None,  # Model details are handled internally by AgentController
            provider=None,
            cost=None,
            updated_title=updated_title  # Include the updated title if it was changed
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error processing chat request: {e}", exc_info=True)
        
        # Provide more specific error messages based on the exception type
        error_detail = {
            "error": "Chat Processing Error",
            "message": "An error occurred while processing your message. Please try again.",
            "type": "general_error"
        }
        
        # Check for specific error types and provide better messages
        error_str = str(e).lower()
        if "404" in error_str or "not found" in error_str:
            error_detail = {
                "error": "Service Not Found",
                "message": f"The AI service is not available. Error: {str(e)}",
                "type": "service_error",
                "technical_details": str(e)
            }
        elif "rate limit" in error_str or "429" in error_str:
            error_detail = {
                "error": "Rate Limit Exceeded",
                "message": f"Too many requests. Error: {str(e)}",
                "type": "rate_limit_error",
                "technical_details": str(e)
            }
        elif "connection" in error_str or "timeout" in error_str:
            error_detail = {
                "error": "Connection Error",
                "message": f"Unable to connect to AI service. Error: {str(e)}",
                "type": "connection_error",
                "technical_details": str(e)
            }
        elif "api key" in error_str or "unauthorized" in error_str:
            error_detail = {
                "error": "Authentication Error",
                "message": f"AI service authentication failed. Error: {str(e)}",
                "type": "auth_error",
                "technical_details": str(e)
            }
        else:
            # For any other errors, include the full error message
            error_detail = {
                "error": "Chat Processing Error",
                "message": f"An error occurred: {str(e)}",
                "type": "general_error",
                "technical_details": str(e)
            }
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        )

# Additional endpoints for research flow actions
class QuestionGenerationRequest(BaseModel):
    mission_id: str
    research_topic: str

class QuestionGenerationResponse(BaseModel):
    questions: List[str]
    mission_id: str

class QuestionRefinementRequest(BaseModel):
    mission_id: str
    user_feedback: str
    current_questions: List[str]

class QuestionRefinementResponse(BaseModel):
    questions: List[str]
    response_message: str

class ResearchApprovalRequest(BaseModel):
    mission_id: str
    final_questions: List[str]
    tool_selection: Dict[str, bool] = {"local_rag": True, "web_search": True}

class ResearchApprovalResponse(BaseModel):
    success: bool
    message: str

@router.post("/chat/generate-questions", response_model=QuestionGenerationResponse)
async def generate_research_questions(
    request: QuestionGenerationRequest,
    current_user: User = Depends(get_current_user_from_cookie),
    agent_controller = Depends(get_user_specific_agent_controller)
):
    """
    DEPRECATED: This endpoint is now obsolete. The initial question generation
    is handled directly within the /chat endpoint's `start_research` action flow.
    This endpoint now returns an empty list to prevent overwriting the correct questions.
    """
    logger.warning(f"Deprecated endpoint /chat/generate-questions called for mission {request.mission_id}. The new workflow handles this in the main /chat endpoint. Returning empty list.")
    
    # Return an empty list to prevent any downstream processing or UI updates.
    return QuestionGenerationResponse(
        questions=[],
        mission_id=request.mission_id
    )

@router.post("/chat/refine-questions", response_model=QuestionRefinementResponse)
async def refine_research_questions(
    request: QuestionRefinementRequest,
    current_user: User = Depends(get_current_user_from_cookie),
    agent_controller = Depends(get_user_specific_agent_controller)
):
    """Refine research questions based on user feedback using UserInteractionManager."""
    if not agent_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI chat service is not available."
        )
    
    try:
        # Use the UserInteractionManager's refine_questions method
        refined_questions, response_message = await agent_controller.user_interaction_manager.refine_questions(
            mission_id=request.mission_id,
            user_feedback=request.user_feedback,
            current_questions=request.current_questions
        )
        
        return QuestionRefinementResponse(
            questions=refined_questions,
            response_message=response_message
        )
    except Exception as e:
        logger.error(f"Error refining questions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refine questions: {str(e)}"
        )

@router.post("/chat/approve-questions", response_model=ResearchApprovalResponse)
async def approve_research_questions(
    request: ResearchApprovalRequest,
    current_user: User = Depends(get_current_user_from_cookie),
    agent_controller = Depends(get_user_specific_agent_controller)
):
    """Approve final questions and start the research process using UserInteractionManager."""
    if not agent_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI chat service is not available."
        )
    
    try:
        # Use the UserInteractionManager's confirm_questions_and_run method
        success = await agent_controller.user_interaction_manager.confirm_questions_and_run(
            mission_id=request.mission_id,
            final_questions=request.final_questions,
            tool_selection=request.tool_selection
        )
        
        if success:
            # Update mission status to indicate research is starting
            agent_controller.context_manager.update_mission_status(
                request.mission_id, 
                "planning"
            )
            
            # Start the actual research execution in the background
            # This is the missing piece - we need to trigger run_mission()
            async def run_research_background():
                try:
                    logger.info(f"Starting background research execution for mission {request.mission_id}")
                    await agent_controller.run_mission(
                        mission_id=request.mission_id,
                        log_queue=None,  # Could add WebSocket support later
                        update_callback=None  # Could add WebSocket support later
                    )
                    logger.info(f"Background research execution completed for mission {request.mission_id}")
                except Exception as research_error:
                    logger.error(f"Background research execution failed for mission {request.mission_id}: {research_error}", exc_info=True)
                    # Update mission status to failed if research execution fails
                    agent_controller.context_manager.update_mission_status(
                        request.mission_id, 
                        "failed", 
                        f"Research execution failed: {str(research_error)}"
                    )
            
            # Start the research execution as a background task
            asyncio.create_task(run_research_background())
            
            logger.info(f"Research approved and background execution started for mission {request.mission_id}")
            
            return ResearchApprovalResponse(
                success=True,
                message="Research questions approved. Research execution has started in the background..."
            )
        else:
            return ResearchApprovalResponse(
                success=False,
                message="Failed to start research process."
            )
    except Exception as e:
        logger.error(f"Error approving questions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve questions: {str(e)}"
        )

@router.get("/chat/status")
async def get_chat_status(
    current_user: User = Depends(get_current_user_from_cookie),
    agent_controller = Depends(get_user_specific_agent_controller)
):
    """Get the status of the chat service."""
    return {
        "status": "available" if agent_controller else "unavailable",
        "user": current_user.username,
        "models_configured": bool(agent_controller)
    }
