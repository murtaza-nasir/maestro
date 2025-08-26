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
from services.websocket_manager import websocket_manager
from api.utils import _make_serializable
from api.locales import get_message

router = APIRouter()
logger = logging.getLogger(__name__)

# Legacy ConnectionManager - kept for backward compatibility during migration
class ConnectionManager:
    """Legacy connection manager - now delegates to WebSocketManager."""
    
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
    Uses the centralized WebSocketManager to prevent duplicate connections.
    """
    connection_id = None
    lang = websocket.query_params.get("lang", "en")
    try:
        # Extract and validate JWT token from query parameters
        token = websocket.query_params.get("token")
        
        if not token:
            logger.debug(f"WebSocket connection rejected: No authentication token for user {user_id}")
            await websocket.close(code=1008, reason=get_message("websockets.authRequired", lang))
            return
        
        # Verify the token
        from auth.security import verify_token
        try:
            username = verify_token(token)
            if username is None:
                logger.debug(f"WebSocket connection rejected: Token verification failed for user {user_id}")
                await websocket.close(code=1008, reason=get_message("websockets.invalidToken", lang))
                return
            logger.debug(f"WebSocket token verification successful for user {username}")
        except Exception as e:
            logger.debug(f"WebSocket token verification error: {str(e)}")
            await websocket.close(code=1008, reason=get_message("websockets.tokenVerificationError", lang))
            return
        
        # Verify user exists in database and matches the user_id
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            from database import crud
            user = crud.get_user_by_username(db, username=username)
            if user is None or str(user.id) != user_id:
                logger.debug(f"WebSocket connection rejected: User mismatch. Expected {user_id}, got {user.id if user else None}")
                await websocket.close(code=1008, reason=get_message("websockets.userMismatch", lang))
                return
        finally:
            db.close()
        
        await websocket.accept()
        
        # Register with WebSocketManager
        connection_id = await websocket_manager.connect(
            websocket=websocket,
            user_id=user_id,
            connection_type='document'
        )
        logger.info(f"Document WebSocket connected for user {user_id} (connection: {connection_id})")
        
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": get_message("websockets.connectedToDocUpdates", lang),
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
        if connection_id:
            await websocket_manager.disconnect(connection_id)
        else:
            manager.disconnect(websocket, user_id)

# Research connection manager - single connection for all missions
research_manager = ConnectionManager()

@router.websocket("/api/ws/research")
async def websocket_research_updates(websocket: WebSocket):
    """
    Single WebSocket endpoint for ALL research functionality.
    Handles updates for all missions using the centralized WebSocketManager.
    """
    connection_id = None
    lang = websocket.query_params.get("lang", "en")
    try:
        # Extract and validate JWT token
        token = websocket.query_params.get("token")
        if not token:
            token = websocket.cookies.get("access_token")
            
        if not token:
            await websocket.close(code=1008, reason=get_message("websockets.missingAuthToken", lang))
            return
            
        # Validate token and get user
        from auth.security import verify_token
        try:
            username = verify_token(token)
            if username is None:
                logger.debug(f"WebSocket connection rejected: Token verification failed")
                await websocket.close(code=1008, reason=get_message("websockets.invalidToken", lang))
                return
            logger.debug(f"WebSocket token verification successful for user: {username}")
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            await websocket.close(code=1008, reason=get_message("websockets.invalidToken", lang))
            return
        
        # Verify user exists in database
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            from database import crud
            user = crud.get_user_by_username(db, username=username)
            if user is None:
                logger.debug(f"WebSocket connection rejected: User not found")
                await websocket.close(code=1008, reason=get_message("websockets.userNotFound", lang))
                return
            user_id = str(user.id)
        finally:
            db.close()
            
        await websocket.accept()
        
        # Register with WebSocketManager
        connection_id = await websocket_manager.connect(
            websocket=websocket,
            user_id=user_id,
            connection_type='research'
        )
        logger.info(f"Research WebSocket connected for user {username} (connection: {connection_id})")
        
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": get_message("websockets.connectedToResearchUpdates", lang),
            "connection_id": connection_id
        }))
        
        # Heartbeat setup
        last_heartbeat = time.time()
        
        async def send_heartbeat():
            while True:
                try:
                    await asyncio.sleep(30)
                    await websocket.send_text(json.dumps({
                        "type": "heartbeat",
                        "timestamp": time.time()
                    }))
                except Exception:
                    break
                    
        heartbeat_task = asyncio.create_task(send_heartbeat())
        
        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                    message = json.loads(data)
                    last_heartbeat = time.time()
                    
                    msg_type = message.get("type")
                    
                    if msg_type == "ping":
                        await websocket_manager.handle_ping(connection_id)
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": message.get("timestamp")
                        }))
                    elif msg_type == "heartbeat_ack":
                        await websocket_manager.handle_ping(connection_id)
                        logger.debug("Heartbeat acknowledged")
                    elif msg_type == "subscribe":
                        # Subscribe to updates for a specific mission
                        mission_id = message.get("mission_id")
                        if mission_id:
                            await websocket_manager.subscribe_to_mission(connection_id, mission_id)
                            logger.info(f"User {username} subscribed to mission {mission_id}")
                            
                            # Send a test message directly to confirm WebSocket works
                            await websocket.send_text(json.dumps({
                                "type": "test_direct_message",
                                "message": get_message("websockets.directTestForMission", lang, mission_id=mission_id),
                                "timestamp": time.time()
                            }))
                            
                            # Send initial data for this mission
                            await send_initial_mission_data(websocket, mission_id, username)
                    elif msg_type == "unsubscribe":
                        # Unsubscribe from a mission
                        mission_id = message.get("mission_id")
                        if mission_id:
                            await websocket_manager.unsubscribe_from_mission(connection_id, mission_id)
                            logger.info(f"User {username} unsubscribed from mission {mission_id}")
                    elif msg_type == "get_logs":
                        # Request logs for a specific mission
                        mission_id = message.get("mission_id")
                        if mission_id:
                            await send_mission_logs(websocket, mission_id, username)
                            
                except asyncio.TimeoutError:
                    if time.time() - last_heartbeat > 120:
                        logger.warning(f"Research WebSocket timeout for {username}")
                        break
                    continue
                except WebSocketDisconnect:
                    logger.info(f"Research WebSocket disconnected for {username}")
                    break
                except Exception as e:
                    logger.error(f"Error in research WebSocket: {e}")
                    break
                    
        finally:
            heartbeat_task.cancel()
            if connection_id:
                await websocket_manager.disconnect(connection_id)
                
    except Exception as e:
        logger.error(f"Research WebSocket error: {e}")
        await websocket.close(code=1011, reason=get_message("websockets.internalError", lang))

async def send_initial_mission_data(websocket: WebSocket, mission_id: str, username: str):
    """Send initial data when subscribing to a mission."""
    try:
        db = next(get_db())
        try:
            # Get mission logs
            logs = db.query(models.MissionExecutionLog).filter(
                models.MissionExecutionLog.mission_id == mission_id
            ).order_by(models.MissionExecutionLog.timestamp.desc()).limit(100).all()
            
            logs_data = [{
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "agent_name": log.agent_name,
                "action": log.action,
                "status": log.status,
                "output_summary": log.output_summary,
                "error_message": log.error_message
            } for log in reversed(logs)]
            
            await websocket.send_text(json.dumps({
                "type": "logs_update",
                "mission_id": mission_id,
                "action": "replace",
                "data": logs_data,
                "timestamp": time.time()
            }))
            
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to send initial mission data: {e}")

async def send_mission_logs(websocket: WebSocket, mission_id: str, username: str):
    """Send logs for a specific mission."""
    await send_initial_mission_data(websocket, mission_id, username)


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
    # Use WebSocketManager for document updates
    await websocket_manager.send_to_user(user_id, message)
    # Also try legacy manager for backward compatibility
    await manager.send_personal_message(json.dumps(message), user_id)

async def send_job_update(user_id: str, update: Dict):
    """Send a job update to a specific user."""
    await manager.send_personal_message(json.dumps(update), user_id)

# Mission update utility functions
async def send_mission_update(mission_id: str, update: Dict):
    """Send a mission update to all research WebSocket clients subscribed to this mission."""
    # Use the centralized WebSocketManager
    serialized_update = _make_serializable(update)
    await websocket_manager.send_to_mission(mission_id, serialized_update)

async def send_notes_update(mission_id: str, new_notes: List[Dict], action: str = "append"):
    """Send notes update to research WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "notes_update",
        "mission_id": mission_id,  # Always include mission_id for routing
        "action": action,  # "append", "replace", "update"
        "data": new_notes,
        "timestamp": time.time()
    })

async def send_plan_update(mission_id: str, plan_data: Dict, action: str = "update"):
    """Send plan update to research WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "plan_update",
        "mission_id": mission_id,  # Always include mission_id for routing
        "action": action,
        "data": plan_data,
        "timestamp": time.time()
    })

async def send_draft_update(mission_id: str, draft_data: str, action: str = "update"):
    """Send draft update to research WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "draft_update",
        "mission_id": mission_id,  # Always include mission_id for routing
        "action": action,
        "data": draft_data,
        "timestamp": time.time()
    })

async def send_logs_update(mission_id: str, new_logs: List[Dict], action: str = "append"):
    """Send logs update to research WebSocket clients."""
    logger.debug(f"Transmitting 'logs_update' message for mission {mission_id} with {len(new_logs)} new logs.")
    await send_mission_update(mission_id, {
        "type": "logs_update",
        "mission_id": mission_id,  # Always include mission_id for routing
        "action": action,
        "data": new_logs,
        "timestamp": time.time()
    })

async def send_status_update(mission_id: str, status: str, metadata: Dict = None):
    """Send status update to research WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "status_update",
        "mission_id": mission_id,  # Always include mission_id for routing
        "status": status,
        "metadata": metadata or {},
        "timestamp": time.time()
    })

async def send_context_update(mission_id: str, context_data: Dict, action: str = "update"):
    """Send mission context update to research WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "context_update",
        "mission_id": mission_id,  # Always include mission_id for routing
        "action": action,
        "data": context_data,
        "timestamp": time.time()
    })

async def send_goal_pad_update(mission_id: str, goals: List[Dict], action: str = "update"):
    """Send goal pad update to research WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "goal_pad_update",
        "mission_id": mission_id,  # Always include mission_id for routing
        "action": action,
        "data": goals,
        "timestamp": time.time()
    })

async def send_thought_pad_update(mission_id: str, thoughts: List[Dict], action: str = "update"):
    """Send thought pad update to research WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "thought_pad_update",
        "mission_id": mission_id,  # Always include mission_id for routing
        "action": action,
        "data": thoughts,
        "timestamp": time.time()
    })

async def send_scratchpad_update(mission_id: str, scratchpad_content: str, action: str = "update"):
    """Send scratchpad update to research WebSocket clients."""
    await send_mission_update(mission_id, {
        "type": "scratchpad_update",
        "mission_id": mission_id,  # Always include mission_id for routing
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
    Uses the centralized WebSocketManager to prevent duplicate connections.
    """
    connection_id = None
    lang = websocket.query_params.get("lang", "en")
    try:
        # Extract and validate JWT token from query parameters
        token = websocket.query_params.get("token")
        
        if not token:
            logger.debug(f"WebSocket connection rejected: No authentication token for writing session {session_id}")
            await websocket.close(code=1008, reason=get_message("websockets.authRequired", lang))
            return
        
        # Verify the token
        from auth.security import verify_token
        try:
            username = verify_token(token)
            if username is None:
                logger.debug(f"WebSocket connection rejected: Token verification failed for writing session {session_id}")
                await websocket.close(code=1008, reason=get_message("websockets.invalidToken", lang))
                return
            logger.debug(f"WebSocket token verification successful for user {username}")
        except Exception as e:
            logger.debug(f"WebSocket token verification error: {str(e)}")
            await websocket.close(code=1008, reason=get_message("websockets.tokenVerificationError", lang))
            return
        
        # Verify user exists in database and owns the writing session
        from database.database import SessionLocal
        db = SessionLocal()
        try:
            from database import crud
            user = crud.get_user_by_username(db, username=username)
            if user is None:
                logger.debug(f"WebSocket connection rejected: User not found for writing session {session_id}")
                await websocket.close(code=1008, reason=get_message("websockets.userNotFound", lang))
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
                await websocket.close(code=1008, reason=get_message("websockets.writingSessionNotFound", lang))
                return
            
            user_id = str(user.id)
                
        finally:
            db.close()
        
        # Accept the connection ONLY after successful authentication
        await websocket.accept()
        
        # Register with WebSocketManager - will close duplicates automatically
        connection_id = await websocket_manager.connect(
            websocket=websocket,
            user_id=user_id,
            connection_type='writing',
            session_id=session_id
        )
        logger.debug(f"WebSocket connection accepted for writing session {session_id}, user: {username}, connection: {connection_id}")
        
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": get_message("websockets.connectedToWritingSession", lang, session_id=session_id),
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
        # Disconnect from WebSocketManager
        if connection_id:
            await websocket_manager.disconnect(connection_id)

# Writing session update utility functions
async def send_writing_update(session_id: str, update: Dict):
    """Send a writing update to all connected clients for this session."""
    # Use the centralized WebSocketManager
    serialized_update = _make_serializable(update)
    await websocket_manager.send_to_session(session_id, serialized_update)

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
