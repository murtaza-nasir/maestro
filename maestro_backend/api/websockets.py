"""
WebSocket endpoints for real-time updates.
"""
import time
import json
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from typing import Dict, List, Any
from sqlalchemy.orm import Session

from database import models
from database.database import get_db
from services.background_document_processor import background_processor
from api.utils import _make_serializable

router = APIRouter()
logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept a WebSocket connection and add it to the manager."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.debug(f"WebSocket connected for user {user_id}. Total connections for user: {len(self.active_connections[user_id])}")
        
        # Also add to background processor
        background_processor.add_websocket_connection(user_id, websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a WebSocket connection from the manager."""
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            except ValueError:
                pass
        
        # Also remove from background processor
        background_processor.remove_websocket_connection(user_id, websocket)
    
    async def send_personal_message(self, message: str, user_id: str):
        """Send a message to all connections for a specific user."""
        if user_id in self.active_connections:
            disconnected = []
            for websocket in self.active_connections[user_id]:
                try:
                    await websocket.send_text(message)
                except:
                    disconnected.append(websocket)
            
            # Remove disconnected websockets
            for websocket in disconnected:
                self.disconnect(websocket, user_id)
    
    async def broadcast(self, message: str):
        """Broadcast a message to all connected users."""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)

# Global connection manager
manager = ConnectionManager()

@router.websocket("/ws/documents/{user_id}")
async def websocket_document_updates(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for real-time document processing updates.
    """
    try:
        # Extract and validate JWT token from query parameters
        token = websocket.query_params.get("token")
        
        if not token:
            logger.debug(f"WebSocket connection rejected: No authentication token for user {user_id}")
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        # Verify the token
        from auth.security import verify_token
        try:
            username = verify_token(token)
            if username is None:
                logger.debug(f"WebSocket connection rejected: Token verification failed for user {user_id}")
                await websocket.close(code=1008, reason="Invalid token")
                return
            logger.debug(f"WebSocket token verification successful for user {username}")
        except Exception as e:
            logger.debug(f"WebSocket token verification error: {str(e)}")
            await websocket.close(code=1008, reason="Token verification error")
            return
        
        # Verify user exists in database and matches the user_id
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            from database import crud
            user = crud.get_user_by_username(db, username=username)
            if user is None or str(user.id) != user_id:
                logger.debug(f"WebSocket connection rejected: User mismatch. Expected {user_id}, got {user.id if user else None}")
                await websocket.close(code=1008, reason="User not found or mismatch")
                return
        finally:
            db.close()
        
        await manager.connect(websocket, user_id)
        
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": "Connected to document updates",
            "user_id": user_id
        }))
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (like ping/pong)
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": message.get("timestamp")
                    }))
                elif message.get("type") == "get_active_jobs":
                    # Send empty jobs list for now
                    await websocket.send_text(json.dumps({
                        "type": "active_jobs",
                        "jobs": []
                    }))
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break
                
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        manager.disconnect(websocket, user_id)

# Mission connection manager
mission_manager = ConnectionManager()

@router.websocket("/api/ws/missions/{mission_id}")
async def websocket_mission_updates(websocket: WebSocket, mission_id: str):
    """
    WebSocket endpoint for real-time mission execution updates.
    """
    try:
        # Extract and validate JWT token from query parameters or cookies
        token = websocket.query_params.get("token")
        token_source = "query parameter"
        
        if not token:
            # Fallback to cookies for backward compatibility
            cookies = websocket.cookies
            token = cookies.get("access_token")
            token_source = "cookie"
            
        # Enhanced logging for authentication debugging
        if token:
            token_preview = token[:10] + "..." if len(token) > 10 else token
            logger.debug(f"WebSocket {token_source} token: {token_preview}")
        else:
            logger.debug(f"No token found in query parameters or cookies")
        
        # Log detailed authentication attempt for debugging
        logger.debug(f"WebSocket auth attempt details:")
        logger.debug(f"  Mission ID: {mission_id}")
        logger.debug(f"  Token present: {bool(token)}")
        logger.debug(f"  Token source: {token_source}")
        logger.debug(f"  Headers: {dict(websocket.headers)}")
        logger.debug(f"  Cookies: {dict(websocket.cookies)}")
        logger.debug(f"  Client host: {websocket.client.host}")
        logger.debug(f"  Query parameters: {dict(websocket.query_params)}")
        
        if not token:
            logger.debug(f"WebSocket connection rejected: No authentication token for mission {mission_id}")
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        # Verify the token with enhanced logging BEFORE accepting connection
        from auth.security import verify_token
        try:
            logger.debug(f"Verifying token: {token}")
            username = verify_token(token)
            if username is None:
                logger.debug(f"WebSocket connection rejected: Token verification returned None for mission {mission_id}")
                await websocket.close(code=1008, reason="Invalid token")
                return
            logger.debug(f"WebSocket token verification successful for user: {username}")
        except Exception as e:
            logger.debug(f"WebSocket token verification error: {str(e)}")
            await websocket.close(code=1008, reason="Token verification error")
            return
        
        # Verify user exists in database BEFORE accepting connection
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            from database import crud
            user = crud.get_user_by_username(db, username=username)
            if user is None:
                logger.debug(f"WebSocket connection rejected: User not found for mission {mission_id}")
                await websocket.close(code=1008, reason="User not found")
                return
        finally:
            db.close()
        
        # Accept the connection ONLY after successful authentication
        await websocket.accept()
        logger.debug(f"WebSocket connection accepted for mission {mission_id}, user: {username}")
        
        # Add to mission manager
        if mission_id not in mission_manager.active_connections:
            mission_manager.active_connections[mission_id] = []
        mission_manager.active_connections[mission_id].append(websocket)
        
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": f"Connected to mission {mission_id} updates",
            "mission_id": mission_id
        }))
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": message.get("timestamp")
                    }))
                elif message.get("type") == "subscribe":
                    # Handle subscription to specific update types
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "event_types": message.get("event_types", [])
                    }))
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Mission WebSocket error: {e}")
                break
                
    except Exception as e:
        logger.error(f"Mission WebSocket connection error: {e}")
    finally:
        # Remove from mission manager
        if mission_id in mission_manager.active_connections:
            try:
                mission_manager.active_connections[mission_id].remove(websocket)
                if not mission_manager.active_connections[mission_id]:
                    del mission_manager.active_connections[mission_id]
            except ValueError:
                pass

# Utility functions for sending updates
async def send_document_update(user_id: str, update: Dict):
    """Send a document update to a specific user."""
    # Format the message for the frontend
    message = {
        "type": "document_progress",
        "doc_id": update.get("doc_id"),
        "document_id": update.get("doc_id"),  # Provide both for compatibility
        "progress": update.get("progress", 0),
        "status": update.get("status", "processing"),
        "error": update.get("error"),
        "user_id": user_id,
        "timestamp": update.get("timestamp")
    }
    logger.debug(f"Sending WebSocket message to user {user_id}: {message}")
    logger.debug(f"Active connections for user {user_id}: {len(manager.active_connections.get(user_id, []))}")
    logger.debug(f"All active connections: {list(manager.active_connections.keys())}")
    await manager.send_personal_message(json.dumps(message), user_id)

async def send_job_update(user_id: str, update: Dict):
    """Send a job update to a specific user."""
    await manager.send_personal_message(json.dumps(update), user_id)

# Mission update utility functions
async def send_mission_update(mission_id: str, update: Dict):
    """Send a mission update to all connected clients for this mission."""
    if mission_id in mission_manager.active_connections:
        disconnected = []
        message = json.dumps(_make_serializable(update))
        for websocket in mission_manager.active_connections[mission_id]:
            try:
                await websocket.send_text(message)
            except:
                disconnected.append(websocket)
        
        # Remove disconnected websockets
        for websocket in disconnected:
            try:
                mission_manager.active_connections[mission_id].remove(websocket)
                if not mission_manager.active_connections[mission_id]:
                    del mission_manager.active_connections[mission_id]
            except ValueError:
                pass

async def send_notes_update(mission_id: str, new_notes: List[Dict], action: str = "append"):
    """Send notes update to mission WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "notes_update",
        "mission_id": mission_id,
        "action": action,  # "append", "replace", "update"
        "data": new_notes,
        "timestamp": time.time()
    })

async def send_plan_update(mission_id: str, plan_data: Dict, action: str = "update"):
    """Send plan update to mission WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "plan_update",
        "mission_id": mission_id,
        "action": action,
        "data": plan_data,
        "timestamp": time.time()
    })

async def send_draft_update(mission_id: str, draft_data: str, action: str = "update"):
    """Send draft update to mission WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "draft_update",
        "mission_id": mission_id,
        "action": action,
        "data": draft_data,
        "timestamp": time.time()
    })

async def send_logs_update(mission_id: str, new_logs: List[Dict], action: str = "append"):
    """Send logs update to mission WebSocket clients."""
    logger.debug(f"Transmitting 'logs_update' message for mission {mission_id} with {len(new_logs)} new logs.")
    await send_mission_update(mission_id, {
        "type": "logs_update",
        "mission_id": mission_id,
        "action": action,
        "data": new_logs,
        "timestamp": time.time()
    })

async def send_status_update(mission_id: str, status: str, metadata: Dict = None):
    """Send status update to mission WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "status_update",
        "mission_id": mission_id,
        "status": status,
        "metadata": metadata or {},
        "timestamp": time.time()
    })

async def send_context_update(mission_id: str, context_data: Dict, action: str = "update"):
    """Send mission context update to mission WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "context_update",
        "mission_id": mission_id,
        "action": action,
        "data": context_data,
        "timestamp": time.time()
    })

async def send_goal_pad_update(mission_id: str, goals: List[Dict], action: str = "update"):
    """Send goal pad update to mission WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "goal_pad_update",
        "mission_id": mission_id,
        "action": action,
        "data": goals,
        "timestamp": time.time()
    })

async def send_thought_pad_update(mission_id: str, thoughts: List[Dict], action: str = "update"):
    """Send thought pad update to mission WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "thought_pad_update",
        "mission_id": mission_id,
        "action": action,
        "data": thoughts,
        "timestamp": time.time()
    })

async def send_scratchpad_update(mission_id: str, scratchpad_content: str, action: str = "update"):
    """Send scratchpad update to mission WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "scratchpad_update",
        "mission_id": mission_id,
        "action": action,
        "data": scratchpad_content,
        "timestamp": time.time()
    })

# Writing session connection manager
writing_manager = ConnectionManager()

@router.websocket("/ws/{session_id}")
async def websocket_writing_updates(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time writing session updates.
    """
    try:
        # Extract and validate JWT token from query parameters
        token = websocket.query_params.get("token")
        
        if not token:
            logger.debug(f"WebSocket connection rejected: No authentication token for writing session {session_id}")
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        # Verify the token
        from auth.security import verify_token
        try:
            username = verify_token(token)
            if username is None:
                logger.debug(f"WebSocket connection rejected: Token verification failed for writing session {session_id}")
                await websocket.close(code=1008, reason="Invalid token")
                return
            logger.debug(f"WebSocket token verification successful for user {username}")
        except Exception as e:
            logger.debug(f"WebSocket token verification error: {str(e)}")
            await websocket.close(code=1008, reason="Token verification error")
            return
        
        # Verify user exists in database and owns the writing session
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            from database import crud
            user = crud.get_user_by_username(db, username=username)
            if user is None:
                logger.debug(f"WebSocket connection rejected: User not found for writing session {session_id}")
                await websocket.close(code=1008, reason="User not found")
                return
            
            # Check if writing session exists and belongs to user
            # WritingSession -> Chat -> User relationship
            writing_session = db.query(models.WritingSession).join(
                models.Chat, models.WritingSession.chat_id == models.Chat.id
            ).filter(
                models.WritingSession.id == session_id,
                models.Chat.user_id == user.id
            ).first()
            
            if not writing_session:
                logger.debug(f"WebSocket connection rejected: Writing session {session_id} not found or not owned by user {username}")
                await websocket.close(code=1008, reason="Writing session not found or access denied")
                return
                
        finally:
            db.close()
        
        # Accept the connection ONLY after successful authentication
        await websocket.accept()
        logger.debug(f"WebSocket connection accepted for writing session {session_id}, user: {username}")
        
        # Add to writing manager
        if session_id not in writing_manager.active_connections:
            writing_manager.active_connections[session_id] = []
        writing_manager.active_connections[session_id].append(websocket)
        
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": f"Connected to writing session {session_id}",
            "session_id": session_id
        }))
        
        # Keep connection alive and handle incoming messages
        # Also send periodic heartbeats to prevent client timeout
        import time
        last_heartbeat = time.time()
        heartbeat_interval = 30  # Send heartbeat every 30 seconds
        
        while True:
            try:
                # Check if we need to send a heartbeat
                current_time = time.time()
                if current_time - last_heartbeat > heartbeat_interval:
                    await websocket.send_text(json.dumps({
                        "type": "heartbeat",
                        "timestamp": current_time
                    }))
                    last_heartbeat = current_time
                
                # Non-blocking receive with timeout
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    message = json.loads(data)
                    
                    if message.get("type") == "ping":
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": message.get("timestamp")
                        }))
                    elif message.get("type") == "agent_status":
                        # Handle agent status updates
                        await websocket.send_text(json.dumps({
                            "type": "agent_status",
                            "status": message.get("status", "idle")
                        }))
                except asyncio.TimeoutError:
                    # No message received, continue to check heartbeat
                    continue
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.debug(f"Writing WebSocket error: {e}")
                break
                
    except Exception as e:
        logger.debug(f"Writing WebSocket connection error: {e}")
    finally:
        # Remove from writing manager
        if session_id in writing_manager.active_connections:
            try:
                writing_manager.active_connections[session_id].remove(websocket)
                if not writing_manager.active_connections[session_id]:
                    del writing_manager.active_connections[session_id]
            except ValueError:
                pass

# Writing session update utility functions
async def send_writing_update(session_id: str, update: Dict):
    """Send a writing update to all connected clients for this session."""
    if session_id in writing_manager.active_connections:
        disconnected = []
        message = json.dumps(_make_serializable(update))
        for websocket in writing_manager.active_connections[session_id]:
            try:
                await websocket.send_text(message)
            except:
                disconnected.append(websocket)
        
        # Remove disconnected websockets
        for websocket in disconnected:
            try:
                writing_manager.active_connections[session_id].remove(websocket)
                if not writing_manager.active_connections[session_id]:
                    del writing_manager.active_connections[session_id]
            except ValueError:
                pass

async def send_agent_status_update(session_id: str, status: str, details: str = ""):
    """Send agent status update to writing session WebSocket clients."""
    await send_writing_update(session_id, {
        "type": "agent_status",
        "session_id": session_id,
        "status": status,
        "details": details,
        "timestamp": time.time()
    })

async def send_streaming_chunk_update(session_id: str, chunk: str):
    """Send streaming content chunk to writing session WebSocket clients."""
    await send_writing_update(session_id, {
        "type": "streaming_chunk",
        "session_id": session_id,
        "chunk": chunk,
        "timestamp": time.time()
    })

async def send_draft_content_update(session_id: str, content: Dict, action: str = "update"):
    """Send draft content update to writing session WebSocket clients."""
    await send_writing_update(session_id, {
        "type": "draft_content_update",
        "session_id": session_id,
        "action": action,
        "data": content,
        "timestamp": time.time()
    })

async def send_chat_title_update(session_id: str, chat_id: str, title: str):
    """Send chat title update to writing session WebSocket clients."""
    await send_writing_update(session_id, {
        "type": "chat_title_update",
        "session_id": session_id,
        "chat_id": chat_id,
        "title": title,
        "timestamp": time.time()
    })

async def send_writing_stats_update(session_id: str, stats_data: Dict[str, Any]):
    """Send writing session stats update to WebSocket clients."""
    await send_writing_update(session_id, {
        "type": "stats_update",
        "session_id": session_id,
        "data": stats_data,
        "timestamp": time.time()
    })
