from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import httpx

from database import crud
from database.database import get_db
from auth.dependencies import get_current_user_from_cookie
from api import schemas
from database.models import User

router = APIRouter()

class SettingsUpdate(schemas.BaseModel):
    settings: schemas.GlobalUserSettings

@router.get("/me/settings", response_model=schemas.GlobalUserSettings)
def get_user_settings(current_user: User = Depends(get_current_user_from_cookie)):
    """Get current user's settings"""
    settings_data = current_user.settings or {}
    ai_endpoints_data = settings_data.get("ai_endpoints", {})
    
    # Migration logic: Convert old format to new unified format
    if ai_endpoints_data and "models" in ai_endpoints_data and "advanced_models" not in ai_endpoints_data:
        # Old format detected - migrate to new format
        old_models = ai_endpoints_data.get("models", {})
        providers = ai_endpoints_data.get("providers", {})
        
        # Find the enabled provider
        enabled_provider = None
        for provider_name, config in providers.items():
            if config.get("enabled", False):
                enabled_provider = provider_name
                break
        
        if not enabled_provider:
            enabled_provider = "openrouter"  # Default fallback
        
        # Get provider config
        provider_config = providers.get(enabled_provider, {})
        base_url = provider_config.get("base_url") or (
            "https://openrouter.ai/api/v1/" if enabled_provider == "openrouter" else
            "https://api.openai.com/v1/" if enabled_provider == "openai" else
            ""
        )
        
        # Create advanced_models from old models
        advanced_models = {}
        for model_type in ["fast", "mid", "intelligent", "verifier"]:
            model_name = old_models.get(model_type, "openai/gpt-4o-mini")
            advanced_models[model_type] = {
                "provider": enabled_provider,
                "api_key": provider_config.get("api_key"),
                "base_url": base_url,
                "model_name": model_name
            }
        
        ai_endpoints_data["advanced_models"] = advanced_models
        # Remove old models field
        ai_endpoints_data.pop("models", None)
    
    # Ensure advanced_models exists with empty structure - user must configure
    if "advanced_models" not in ai_endpoints_data:
        ai_endpoints_data["advanced_models"] = {
            "fast": {
                "provider": None,
                "api_key": None,
                "base_url": None,
                "model_name": None
            },
            "mid": {
                "provider": None, 
                "api_key": None,
                "base_url": None,
                "model_name": None
            },
            "intelligent": {
                "provider": None,
                "api_key": None,
                "base_url": None,
                "model_name": None
            },
            "verifier": {
                "provider": None,
                "api_key": None,
                "base_url": None,
                "model_name": None
            }
        }
    
    # Ensure we always have a valid ai_endpoints structure
    if not ai_endpoints_data:
        ai_endpoints_data = {}
    
    # Ensure providers exists
    if "providers" not in ai_endpoints_data:
        ai_endpoints_data["providers"] = {
            "openrouter": {"enabled": True, "api_key": None, "base_url": "https://openrouter.ai/api/v1/"},
            "openai": {"enabled": False, "api_key": None, "base_url": "https://api.openai.com/v1/"},
            "custom": {"enabled": False, "api_key": None, "base_url": None}
        }
    
    # Ensure advanced_models is never None - provide empty structure requiring user configuration
    if "advanced_models" not in ai_endpoints_data or ai_endpoints_data["advanced_models"] is None:
        ai_endpoints_data["advanced_models"] = {
            "fast": {
                "provider": None,
                "api_key": None,
                "base_url": None,
                "model_name": None
            },
            "mid": {
                "provider": None, 
                "api_key": None,
                "base_url": None,
                "model_name": None
            },
            "intelligent": {
                "provider": None,
                "api_key": None,
                "base_url": None,
                "model_name": None
            },
            "verifier": {
                "provider": None,
                "api_key": None,
                "base_url": None,
                "model_name": None
            }
        }
    
    return schemas.GlobalUserSettings(
        ai_endpoints=ai_endpoints_data,
        search=settings_data.get("search"),
        research_parameters=settings_data.get("research_parameters"),
        writing_settings=settings_data.get("writing_settings"),
        appearance=schemas.AppearanceSettings(
            theme=current_user.theme,
            color_scheme=current_user.color_scheme
        )
    )

@router.put("/me/settings", response_model=schemas.GlobalUserSettings)
def update_user_settings(
    settings_update: SettingsUpdate,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Update current user's settings"""
    settings_dict = settings_update.settings.dict(exclude_unset=True)
    
    # Separate appearance settings from other settings
    appearance_settings = settings_dict.pop("appearance", None)
    
    # Update the main settings JSON blob
    if settings_dict:
        updated_user = crud.update_user_settings(db, current_user.id, settings_dict)
        if not updated_user:
            raise HTTPException(status_code=500, detail="Failed to update user settings")
    else:
        updated_user = current_user

    # Update appearance settings directly on the user model
    if appearance_settings:
        updated_user = crud.update_user_appearance(db, current_user.id, schemas.AppearanceSettings(**appearance_settings))
        if not updated_user:
            raise HTTPException(status_code=500, detail="Failed to update appearance settings")

    return get_user_settings(updated_user)

@router.get("/me/profile", response_model=schemas.UserProfile)
def get_user_profile(current_user: User = Depends(get_current_user_from_cookie)):
    """Get current user's profile"""
    return {
        "full_name": current_user.full_name,
        "location": current_user.location,
        "job_title": current_user.job_title,
    }

@router.put("/me/profile", response_model=schemas.UserProfile)
def update_user_profile(
    profile_update: schemas.UserProfileUpdate,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Update current user's profile"""
    updated_user = crud.update_user_profile(db, current_user.id, profile_update)
    
    if not updated_user:
        raise HTTPException(status_code=500, detail="Failed to update user profile")
    
    return {
        "full_name": updated_user.full_name,
        "location": updated_user.location,
        "job_title": updated_user.job_title,
    }

@router.post("/me/settings/test-connection")
async def test_ai_connection(
    connection_config: Dict[str, Any],
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Test AI endpoint connection"""
    try:
        provider = connection_config.get("provider", "openrouter")
        api_key = connection_config.get("api_key")
        base_url = connection_config.get("base_url", "https://openrouter.ai/api/v1/")
        
        # Validate base URL format
        if not base_url:
            raise HTTPException(status_code=400, detail="Base URL is required")
        
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise HTTPException(status_code=400, detail="Base URL must start with 'http://' or 'https://'")
        
        # For OpenRouter and OpenAI, API key is required
        if provider in ["openrouter", "openai"] and not api_key:
            raise HTTPException(status_code=400, detail="API key is required for this provider")
        
        # Prepare headers - only add Authorization if we have an API key
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        # Test connection
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}models",
                headers=headers
            )
            response.raise_for_status()
            return {"success": True, "message": "Connection successful"}
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Connection failed: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Connection test failed: {str(e)}"
        )

@router.get("/me/settings/models")
async def get_available_models(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Get available models from configured AI provider"""
    try:
        # Get user settings
        settings = current_user.settings or {}
        ai_endpoints = settings.get("ai_endpoints", {})
        providers = ai_endpoints.get("providers", {})
        
        # Determine which provider to use
        target_provider = None
        provider_config = None
        
        if provider:
            # Use the specified provider if provided
            target_provider = provider
            if provider in providers:
                provider_config = providers[provider]
            else:
                # Use default config for the provider
                if provider == "openrouter":
                    provider_config = {"api_key": None, "base_url": "https://openrouter.ai/api/v1/"}
                elif provider == "openai":
                    provider_config = {"api_key": None, "base_url": "https://api.openai.com/v1/"}
                else:
                    provider_config = {"api_key": None, "base_url": ""}
        else:
            # Find the first enabled provider
            for provider_name, config in providers.items():
                if config.get("enabled", False):
                    target_provider = provider_name
                    provider_config = config
                    break
        
        if not target_provider or not provider_config:
            # Fallback to environment variables
            from ai_researcher.config import (
                FAST_LLM_PROVIDER, MID_LLM_PROVIDER, INTELLIGENT_LLM_PROVIDER,
                OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
                LOCAL_LLM_API_KEY, LOCAL_LLM_BASE_URL
            )
            
            target_provider = FAST_LLM_PROVIDER
            provider_config = {
                "api_key": OPENROUTER_API_KEY if target_provider == "openrouter" else LOCAL_LLM_API_KEY,
                "base_url": OPENROUTER_BASE_URL if target_provider == "openrouter" else LOCAL_LLM_BASE_URL
            }
        
        # Override with query parameters if provided (for draft settings)
        if api_key:
            provider_config["api_key"] = api_key
        if base_url:
            provider_config["base_url"] = base_url
        
        # For advanced mode, check if we have API key from advanced_models
        if not provider_config.get("api_key"):
            advanced_models = ai_endpoints.get("advanced_models", {})
            # Try to get API key from any model using this provider
            for model_config in advanced_models.values():
                if model_config.get("provider") == target_provider and model_config.get("api_key"):
                    provider_config["api_key"] = model_config["api_key"]
                    if not provider_config.get("base_url"):
                        provider_config["base_url"] = model_config.get("base_url", "")
                    break
        
        # For OpenRouter and OpenAI, API key is required
        if target_provider in ["openrouter", "openai"] and not provider_config.get("api_key"):
            raise HTTPException(status_code=400, detail=f"No API key configured for provider: {target_provider}")
        
        # Fetch models from provider
        final_base_url = provider_config.get("base_url", "https://openrouter.ai/api/v1/")
        final_api_key = provider_config.get("api_key")
        
        # Validate base URL format
        if not final_base_url:
            raise HTTPException(status_code=400, detail="Base URL is required")
        
        if not (final_base_url.startswith("http://") or final_base_url.startswith("https://")):
            raise HTTPException(status_code=400, detail="Base URL must start with 'http://' or 'https://'")
        
        # Prepare headers - only add Authorization if we have an API key
        headers = {}
        if final_api_key:
            headers["Authorization"] = f"Bearer {final_api_key}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{final_base_url}models",
                headers=headers
            )
            response.raise_for_status()
            models_data = response.json()
            
            # Extract model names
            if "data" in models_data:
                model_names = [model["id"] for model in models_data["data"]]
            else:
                model_names = []
            
            return {"provider": target_provider, "models": model_names}
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Failed to fetch models: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch models: {str(e)}"
        )
