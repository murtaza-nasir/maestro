"""
Centralized WebSocket Manager for handling all WebSocket connections.
Provides thread-safe connection management, message queuing, and deduplication.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import threading
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


@dataclass
class WebSocketConnection:
    """Represents a WebSocket connection with metadata."""
    websocket: WebSocket
    user_id: str
    connection_id: str
    connection_type: str  # 'research', 'writing', 'document'
    session_id: Optional[str] = None  # For writing sessions
    mission_ids: Set[str] = field(default_factory=set)  # For research missions
    connected_at: datetime = field(default_factory=datetime.now)
    last_ping: datetime = field(default_factory=datetime.now)
    message_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    is_alive: bool = True


@dataclass
class QueuedMessage:
    """Represents a message queued for delivery."""
    message_id: str
    content: Dict[str, Any]
    target_connections: List[str]
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3


class WebSocketManager:
    """
    Singleton WebSocket manager for centralized connection handling.
    Thread-safe and handles message queuing, deduplication, and retry logic.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._connections: Dict[str, WebSocketConnection] = {}
        self._user_connections: Dict[str, Set[str]] = defaultdict(set)
        self._session_connections: Dict[str, Set[str]] = defaultdict(set)
        self._mission_subscriptions: Dict[str, Set[str]] = defaultdict(set)
        self._message_cache: Dict[str, float] = {}  # For deduplication
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._processor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        logger.info("WebSocketManager initialized")

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        connection_type: str,
        session_id: Optional[str] = None
    ) -> str:
        """
        Register a new WebSocket connection.
        Returns the connection ID.
        """
        async with self._lock:
            # Check for existing connections and close duplicates
            if session_id and connection_type == 'writing':
                # For writing sessions, close any existing connections for the same session
                existing = [
                    conn_id for conn_id in self._session_connections.get(session_id, set())
                    if conn_id in self._connections
                ]
                for conn_id in existing:
                    logger.info(f"Closing duplicate writing connection {conn_id} for session {session_id}")
                    await self._close_connection(conn_id)
            
            # Create new connection
            connection_id = str(uuid.uuid4())
            connection = WebSocketConnection(
                websocket=websocket,
                user_id=user_id,
                connection_id=connection_id,
                connection_type=connection_type,
                session_id=session_id
            )
            
            # Store connection
            self._connections[connection_id] = connection
            self._user_connections[user_id].add(connection_id)
            
            if session_id:
                self._session_connections[session_id].add(connection_id)
            
            # Start background tasks if not running
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_stale_connections())
            if self._processor_task is None or self._processor_task.done():
                self._processor_task = asyncio.create_task(self._process_message_queue())
            
            logger.info(f"WebSocket connected: {connection_id} (user: {user_id}, type: {connection_type})")
            return connection_id

    async def disconnect(self, connection_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            await self._close_connection(connection_id)

    async def _close_connection(self, connection_id: str):
        """Internal method to close and cleanup a connection."""
        if connection_id not in self._connections:
            return
            
        connection = self._connections[connection_id]
        connection.is_alive = False
        
        # Remove from all registries
        self._user_connections[connection.user_id].discard(connection_id)
        
        if connection.session_id:
            self._session_connections[connection.session_id].discard(connection_id)
        
        # Remove from mission subscriptions
        for mission_id in list(connection.mission_ids):
            self._mission_subscriptions[mission_id].discard(connection_id)
        
        # Close WebSocket if still open
        try:
            await connection.websocket.close()
        except Exception:
            pass
        
        # Remove connection
        del self._connections[connection_id]
        logger.info(f"WebSocket disconnected: {connection_id}")

    async def subscribe_to_mission(self, connection_id: str, mission_id: str):
        """Subscribe a connection to mission updates."""
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].mission_ids.add(mission_id)
                self._mission_subscriptions[mission_id].add(connection_id)
                logger.debug(f"Connection {connection_id} subscribed to mission {mission_id}")

    async def unsubscribe_from_mission(self, connection_id: str, mission_id: str):
        """Unsubscribe a connection from mission updates."""
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].mission_ids.discard(mission_id)
                self._mission_subscriptions[mission_id].discard(connection_id)
                logger.debug(f"Connection {connection_id} unsubscribed from mission {mission_id}")

    async def send_to_user(self, user_id: str, message: Dict[str, Any]):
        """Send a message to all connections for a specific user."""
        message_id = str(uuid.uuid4())
        message['_msg_id'] = message_id
        
        async with self._lock:
            connection_ids = list(self._user_connections.get(user_id, set()))
        
        if connection_ids:
            await self._queue_message(message, connection_ids)

    async def send_to_session(self, session_id: str, message: Dict[str, Any]):
        """Send a message to all connections for a specific session."""
        message_id = str(uuid.uuid4())
        message['_msg_id'] = message_id
        
        async with self._lock:
            connection_ids = list(self._session_connections.get(session_id, set()))
        
        if connection_ids:
            await self._queue_message(message, connection_ids)

    async def send_to_mission(self, mission_id: str, message: Dict[str, Any]):
        """Send a message to all connections subscribed to a mission."""
        message_id = str(uuid.uuid4())
        message['_msg_id'] = message_id
        message['mission_id'] = mission_id  # Ensure mission_id is in message
        
        message_type = message.get('type', 'unknown')
        logger.info(f"WebSocketManager.send_to_mission called for mission {mission_id}, type: {message_type}")
        
        async with self._lock:
            connection_ids = list(self._mission_subscriptions.get(mission_id, set()))
        
        if connection_ids:
            logger.info(f"Found {len(connection_ids)} subscribers for mission {mission_id}, queuing message type: {message_type}")
            await self._queue_message(message, connection_ids)
        else:
            logger.warning(f"No subscribers for mission {mission_id}, message type: {message_type} will not be sent")

    async def send_to_connection(self, connection_id: str, message: Dict[str, Any]):
        """Send a message to a specific connection."""
        message_id = str(uuid.uuid4())
        message['_msg_id'] = message_id
        
        if connection_id in self._connections:
            await self._queue_message(message, [connection_id])

    async def broadcast(self, message: Dict[str, Any], connection_type: Optional[str] = None):
        """Broadcast a message to all connections or specific type."""
        message_id = str(uuid.uuid4())
        message['_msg_id'] = message_id
        
        async with self._lock:
            if connection_type:
                connection_ids = [
                    cid for cid, conn in self._connections.items()
                    if conn.connection_type == connection_type
                ]
            else:
                connection_ids = list(self._connections.keys())
        
        if connection_ids:
            await self._queue_message(message, connection_ids)

    async def _queue_message(self, message: Dict[str, Any], connection_ids: List[str]):
        """Queue a message for delivery with deduplication."""
        message_id = message.get('_msg_id', str(uuid.uuid4()))
        
        # Check for duplicate messages (within 1 second window)
        cache_key = f"{json.dumps(message, sort_keys=True)}:{','.join(sorted(connection_ids))}"
        current_time = time.time()
        
        if cache_key in self._message_cache:
            if current_time - self._message_cache[cache_key] < 1.0:
                logger.debug(f"Duplicate message detected, skipping: {message_id}")
                return
        
        self._message_cache[cache_key] = current_time
        
        # Clean old cache entries
        if len(self._message_cache) > 1000:
            cutoff_time = current_time - 60
            self._message_cache = {
                k: v for k, v in self._message_cache.items()
                if v > cutoff_time
            }
        
        # Queue the message
        queued_message = QueuedMessage(
            message_id=message_id,
            content=message,
            target_connections=connection_ids
        )
        
        await self._message_queue.put(queued_message)

    async def _process_message_queue(self):
        """Background task to process queued messages."""
        logger.info("WebSocketManager message queue processor started")
        while True:
            try:
                # Get message from queue
                queued_msg = await self._message_queue.get()
                
                message_type = queued_msg.content.get('type', 'unknown')
                mission_id = queued_msg.content.get('mission_id', 'unknown')
                logger.info(f"Processing queued message {queued_msg.message_id}, type: {message_type}, mission: {mission_id}, targets: {len(queued_msg.target_connections)}")
                
                # Send to all target connections
                failed_connections = []
                successful_sends = 0
                for conn_id in queued_msg.target_connections:
                    if conn_id not in self._connections:
                        logger.warning(f"Connection {conn_id} not found in active connections")
                        continue
                    
                    connection = self._connections[conn_id]
                    if not connection.is_alive:
                        logger.warning(f"Connection {conn_id} is not alive")
                        failed_connections.append(conn_id)
                        continue
                    
                    try:
                        message_text = json.dumps(queued_msg.content)
                        await connection.websocket.send_text(message_text)
                        successful_sends += 1
                        logger.info(f"Successfully sent {message_type} message to connection {conn_id} for mission {mission_id}")
                    except Exception as e:
                        logger.error(f"Failed to send message to {conn_id}: {e}")
                        failed_connections.append(conn_id)
                
                if successful_sends > 0:
                    logger.info(f"Message {queued_msg.message_id} sent to {successful_sends} connections")
                else:
                    logger.warning(f"Message {queued_msg.message_id} failed to send to any connections")
                
                # Retry failed messages
                if failed_connections and queued_msg.retry_count < queued_msg.max_retries:
                    queued_msg.retry_count += 1
                    queued_msg.target_connections = failed_connections
                    await asyncio.sleep(1)  # Wait before retry
                    await self._message_queue.put(queued_msg)
                
                # Clean up dead connections
                for conn_id in failed_connections:
                    if queued_msg.retry_count >= queued_msg.max_retries:
                        await self.disconnect(conn_id)
                
            except Exception as e:
                logger.error(f"Error processing message queue: {e}")
                await asyncio.sleep(1)

    async def _cleanup_stale_connections(self):
        """Background task to cleanup stale connections."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                current_time = datetime.now()
                stale_timeout = timedelta(minutes=5)
                
                async with self._lock:
                    stale_connections = [
                        conn_id for conn_id, conn in self._connections.items()
                        if current_time - conn.last_ping > stale_timeout
                    ]
                
                for conn_id in stale_connections:
                    logger.info(f"Cleaning up stale connection: {conn_id}")
                    await self.disconnect(conn_id)
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

    async def handle_ping(self, connection_id: str):
        """Update last ping time for a connection."""
        if connection_id in self._connections:
            self._connections[connection_id].last_ping = datetime.now()

    def get_connection_info(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific connection."""
        if connection_id not in self._connections:
            return None
        
        conn = self._connections[connection_id]
        return {
            'connection_id': conn.connection_id,
            'user_id': conn.user_id,
            'connection_type': conn.connection_type,
            'session_id': conn.session_id,
            'mission_ids': list(conn.mission_ids),
            'connected_at': conn.connected_at.isoformat(),
            'last_ping': conn.last_ping.isoformat(),
            'is_alive': conn.is_alive
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about current connections."""
        return {
            'total_connections': len(self._connections),
            'connections_by_type': {
                conn_type: sum(1 for c in self._connections.values() if c.connection_type == conn_type)
                for conn_type in ['research', 'writing', 'document']
            },
            'unique_users': len(self._user_connections),
            'active_sessions': len(self._session_connections),
            'active_missions': len(self._mission_subscriptions),
            'queued_messages': self._message_queue.qsize(),
            'cache_size': len(self._message_cache)
        }


# Global instance
websocket_manager = WebSocketManager()