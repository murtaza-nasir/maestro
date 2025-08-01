#!/usr/bin/env python3
"""
Debug script to check what's actually stored in the mission_execution_logs table
"""
import sys
import os
sys.path.append('/app')

from database.database import SessionLocal
from database.models import MissionExecutionLog
from sqlalchemy import desc

def check_db_logs():
    db = SessionLocal()
    try:
        # Get recent logs for the mission
        mission_id = 'ad1890bb-2ef0-4522-9ee8-6fcbd822279e'
        
        print(f"Checking logs for mission: {mission_id}")
        print("=" * 80)
        
        # Get all logs for this mission
        logs = db.query(MissionExecutionLog).filter(
            MissionExecutionLog.mission_id == mission_id
        ).order_by(desc(MissionExecutionLog.timestamp)).all()
        
        print(f"Found {len(logs)} logs in database")
        print()
        
        # Check different types of logs
        logs_with_cost = []
        logs_without_cost = []
        
        for i, log in enumerate(logs):
            print(f"Log {i+1}:")
            print(f"  Agent: {log.agent_name}")
            print(f"  Action: {log.action}")
            print(f"  Cost: {log.cost} (type: {type(log.cost)})")
            print(f"  Prompt tokens: {log.prompt_tokens}")
            print(f"  Completion tokens: {log.completion_tokens}")
            print(f"  Native tokens: {log.native_tokens}")
            print(f"  Model details: {log.model_details}")
            print(f"  Model details type: {type(log.model_details)}")
            
            if log.model_details:
                print(f"  Model details keys: {list(log.model_details.keys()) if isinstance(log.model_details, dict) else 'Not a dict'}")
                if isinstance(log.model_details, dict):
                    print(f"  Model details cost: {log.model_details.get('cost')}")
                    print(f"  Model details prompt_tokens: {log.model_details.get('prompt_tokens')}")
                    print(f"  Model details completion_tokens: {log.model_details.get('completion_tokens')}")
            
            if log.cost is not None or log.prompt_tokens is not None:
                logs_with_cost.append(log)
            else:
                logs_without_cost.append(log)
            
            print("-" * 40)
        
        print(f"\nSummary:")
        print(f"Logs with cost/token data: {len(logs_with_cost)}")
        print(f"Logs without cost/token data: {len(logs_without_cost)}")
        
        if logs_with_cost:
            print(f"\nFirst log with cost data:")
            log = logs_with_cost[0]
            print(f"  Agent: {log.agent_name}")
            print(f"  Action: {log.action}")
            print(f"  Cost: {log.cost}")
            print(f"  Model details: {log.model_details}")
        
    finally:
        db.close()

if __name__ == "__main__":
    check_db_logs()
