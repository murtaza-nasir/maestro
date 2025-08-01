"""
Tools specifically designed for the Enhanced Collaborative Writing Agent.
"""
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Tool Input Schemas ---

class RespondToUserInput(BaseModel):
    """Input schema for responding directly to the user."""
    message: str = Field(..., description="The message to send to the user.")

class DocumentSearchInput(BaseModel):
    """Input schema for searching within the document group."""
    query: str = Field(..., description="The search query.")
    document_group_id: str = Field(..., description="The ID of the document group to search within.")
    max_results: int = Field(default=5, description="Maximum number of search results to return.")

class WebSearchInput(BaseModel):
    """Input schema for performing a web search."""
    query: str = Field(..., description="The web search query.")

class AddSectionInput(BaseModel):
    """Input schema for adding a new section to the document."""
    title: str = Field(..., description="The title of the new section.")
    target_element_id: Optional[str] = Field(default="doc_root", description="The ID of the element (section or paragraph) to insert the new section after. Defaults to 'doc_root' to add to the end of the document.")

class AddParagraphInput(BaseModel):
    """Input schema for adding a new paragraph to a section."""
    content: str = Field(..., description="The content of the new paragraph.")
    section_id: str = Field(..., description="The ID of the section to add the paragraph to.")
    references: Optional[List[str]] = Field(default_factory=list, description="A list of reference IDs to associate with the paragraph.")

class ProposeAndAddParagraphInput(BaseModel):
    """Input schema for proposing a new paragraph."""
    section_id: str = Field(..., description="The ID of the section where the paragraph will be added.")
    prompt: str = Field(..., description="A prompt or topic for the LLM to generate the paragraph content.")
    references: Optional[List[str]] = Field(default_factory=list, description="A list of reference IDs to associate with the paragraph.")

# --- Tool Implementations (will be connected to services) ---

# Note: These tool implementations now expect 'agent_controller' to be passed in the arguments
# by the BaseAgent's _execute_tool method. This provides access to necessary services.

async def respond_to_user(message: str, **kwargs) -> dict:
    """
    Sends a direct message to the user. Use this when a direct answer is needed
    or to confirm completion of a task.
    """
    return {"status": "message_sent", "message": message}

async def document_search(query: str, document_group_id: str, max_results: int = 5, agent_controller=None, **kwargs) -> dict:
    """
    Searches for relevant information within the currently selected document group.
    """
    if not agent_controller or not hasattr(agent_controller, 'retriever'):
        return {"error": "Retriever service not available."}
    
    filter_metadata = {"document_group_id": document_group_id}
    results = await agent_controller.retriever.retrieve(query, n_results=max_results, filter_metadata=filter_metadata)
    return {"status": "success", "results": results}

async def web_search(query: str, agent_controller=None, **kwargs) -> dict:
    """
    Performs a web search to find external, up-to-date information.
    """
    if not agent_controller or not hasattr(agent_controller, 'tool_registry') or not agent_controller.tool_registry.get_tool('web_search'):
         return {"error": "Web search tool not available in the main registry."}
    
    # The "real" web_search tool is likely in the main controller's registry.
    # We are calling it from here.
    web_search_tool = agent_controller.tool_registry.get_tool('web_search')
    result = await web_search_tool.implementation(query=query)
    return result


async def add_section(title: str, target_element_id: str = "doc_root", writing_context_manager=None, draft_id: str = None, user_id: int = None, **kwargs) -> dict:
    """
    Adds a new section to the document.
    """
    if not all([writing_context_manager, draft_id, user_id]):
        return {"error": "Missing required parameters: writing_context_manager, draft_id, or user_id."}
        
    doc_service = writing_context_manager.get_document_structure_service()
    result = await doc_service.insert_section_after(
        draft_id=draft_id,
        target_element_id=target_element_id,
        title=title,
        level=1, # Assuming level 1 for now
        user_id=user_id
    )
    return result

async def add_paragraph(section_id: str, content: str, references: List[str] = [], writing_context_manager=None, draft_id: str = None, user_id: int = None, **kwargs) -> dict:
    """
    Adds a new paragraph to a specified section.
    """
    if not all([writing_context_manager, draft_id, user_id]):
        return {"error": "Missing required parameters: writing_context_manager, draft_id, or user_id."}

    try:
        doc_service = writing_context_manager.get_document_structure_service()
        
        # Insert paragraph as first child of the specified section
        result = await doc_service.insert_paragraph_after(
            draft_id=draft_id,
            target_element_id=section_id,
            content=content,
            references=references,
            user_id=user_id
        )
        return result
    except Exception as e:
        error_msg = str(e)
        if "Target element not found" in error_msg:
            # Try to get the current document structure to help with debugging
            try:
                doc_service = writing_context_manager.get_document_structure_service()
                draft = await doc_service.get_draft_with_validation(draft_id, user_id)
                structure = draft.content
                return {
                    "error": f"Target section '{section_id}' not found in document. Current document structure: {str(structure)[:500]}..."
                }
            except Exception:
                pass
        return {"error": f"Error executing tool 'add_paragraph': {error_msg}"}

async def propose_and_add_paragraph(
    section_id: str, 
    prompt: str, 
    references: List[str] = [],
    model_dispatcher=None,
    content_generation_prompt_creator=None,
    context=None,
    **kwargs
) -> dict:
    """
    Generates content for a paragraph, then returns a proposal for the user to confirm.
    """
    if not all([model_dispatcher, content_generation_prompt_creator, context]):
        return {"error": "Missing required parameters for content generation."}

    # 1. Generate content using the LLM
    generation_prompt = content_generation_prompt_creator(prompt, context)
    llm_response, _ = await model_dispatcher.get_completion(
        prompt=generation_prompt,
        agent_mode="writing_content_generator"
    )
    
    if not llm_response or not llm_response.choices:
        return {"error": "Failed to generate content from the LLM."}
        
    generated_content = llm_response.choices[0].message.content.strip()

    # 2. Return a proposal object
    return {
        "is_proposal": True,
        "message": f"I have drafted the following content based on your request:\n\n---\n\n{generated_content}\n\n---\n\nShall I add this to the document?",
        "confirmation_required": True,
        "tool_name": "propose_and_add_paragraph", # The original tool
        "arguments": { # The arguments needed to execute the final action
            "section_id": section_id,
            "content": generated_content,
            "references": references
        }
    }
