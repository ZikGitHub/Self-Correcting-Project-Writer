from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"

class ProjectState(BaseModel):
    task: str = Field(description="The user's project request")
    # Project Context

    project_dir: Optional[str] = Field(default=None, description="Path to the unique project output directory")
    
    # Hierarchical Planning
    modules: Optional[List[Dict[str, str]]] = Field(default=None, description="High-level modules/folders")
    plan: Optional[List[Dict[str, str]]] = Field(default=None, description="Detailed file list with purposes")

    files: Dict[str, str] = Field(default_factory=dict, description="Map of relative path -> Generated Code")
    
    # Iteration & Status
    execution_status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    iteration: int = Field(default=0)
    max_iterations: int = Field(default=5)

    
    model_config = {"extra": "ignore"}
