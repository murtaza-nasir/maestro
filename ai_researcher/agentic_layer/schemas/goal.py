# ai_researcher/agentic_layer/schemas/goal.py
import uuid
import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

class GoalEntry(BaseModel):
    """Represents a single goal or guiding thought within the mission's goal pad."""
    goal_id: str = Field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:8]}", description="Unique identifier for the goal.")
    text: str = Field(..., description="The textual content of the goal or guiding thought.")
    status: Literal["active", "addressed", "obsolete"] = Field("active", description="Current status of the goal.")
    source_agent: Optional[str] = Field(None, description="The name of the agent that added this goal (optional).")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now, description="Timestamp when the goal was created.")
    # parent_goal_id: Optional[str] = Field(None, description="ID of the parent goal if this is a sub-goal (optional).")

    class Config:
        # Example configuration if needed, e.g., for ORM mode or extra fields
        # from_attributes = True
        pass
