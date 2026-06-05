import asyncio
import json
import os
import shutil
from fastapi import FastAPI, BackgroundTasks, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from src.graph.graph import app as workflow_app
from src.graph.state import ProjectState, ExecutionStatus
from src.tools.logger import logger
from src.tools.sse_handler import log_queue
app = FastAPI()

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProjectRequest(BaseModel):
    task: str
    project_name: Optional[str] = None
    project_dir: Optional[str] = None

class CreateProjectRequest(BaseModel):
    name: str

# Custom log stream for SSE
async def log_streamer():
    from src.tools.sse_handler import active_clients, log_history
    
    # Create private queue for this client connection
    client_queue = asyncio.Queue()
    
    # Standard queue adapter to allow sse_handler to write synchronously
    class QueueAdapter:
        def put_nowait(self, item):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(client_queue.put_nowait, item)
                else:
                    client_queue.put_nowait(item)
            except Exception:
                pass
    
    adapter = QueueAdapter()
    active_clients.append(adapter)
    
    add_terminal_log("SSE: Stream connection established")
    
    try:
        # First, yield the entire existing log history
        for msg in list(log_history):
            yield f"data: {json.dumps({'message': msg})}\n\n"
            
        # Now, yield new log messages as they arrive in the private queue
        while True:
            try:
                try:
                    msg = await asyncio.wait_for(client_queue.get(), timeout=15.0)
                    yield f"data: {json.dumps({'message': msg})}\n\n"
                except asyncio.TimeoutError:
                    # Send ping/heartbeat to keep connection alive
                    yield ": ping\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
    finally:
        if adapter in active_clients:
            active_clients.remove(adapter)

def add_terminal_log(msg):
    from src.tools.sse_handler import add_log
    add_log(msg)

@app.get("/projects")
async def list_projects():
    """List all project folders in the output directory."""
    projects = [d for d in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, d))]
    return {"projects": sorted(projects)}

@app.post("/create_project")
async def create_project(request: CreateProjectRequest):
    """Create a new project directory in output."""
    project_path = os.path.join(OUTPUT_DIR, request.name)
    if os.path.exists(project_path):
        return {"error": "Project already exists", "status": "exists"}
    os.makedirs(project_path, exist_ok=True)
    return {"status": "created", "project_name": request.name}

def get_directory_tree(path, project_root):
    """Recursively build a directory tree."""
    tree = []
    ignore_dirs = {'.git', 'venv', '.venv', '__pycache__', 'node_modules', '.gemini'}
    
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir():
                    if entry.name in ignore_dirs:
                        continue
                    tree.append({
                        "name": entry.name,
                        "type": "directory",
                        "path": os.path.relpath(entry.path, project_root).replace("\\", "/"),
                        "children": get_directory_tree(entry.path, project_root)
                    })
                else:
                    tree.append({
                        "name": entry.name,
                        "type": "file",
                        "path": os.path.relpath(entry.path, project_root).replace("\\", "/"),
                    })
    except Exception as e:
        logger.error(f"Error scanning directory {path}: {str(e)}")
        
    # Sort: directories first, then files, both alphabetically
    return sorted(tree, key=lambda x: (x["type"] != "directory", x["name"].lower()))

@app.get("/files")
async def get_files(project: str = Query(..., description="The name of the project folder")):
    # Scan the specific project directory
    project_root = os.path.join(OUTPUT_DIR, project)
    logger.info(f"API: Scanning project directory: {project_root}")
    
    if not os.path.exists(project_root):
        logger.warning(f"API: Project directory not found: {project_root}")
        return {"error": "Project not found", "tree": []}
    
    tree = get_directory_tree(project_root, project_root)
    logger.info(f"API: Found {len(tree)} items at root of {project}")
    return {"tree": tree, "project_dir": project_root}

@app.get("/browse")
async def browse_path(path: str = Query(None, description="Absolute path to browse")):
    """Browse the filesystem for folder selection."""
    if not path or path == "undefined" or path == "null" or path == "":
        # Return drives on Windows or root on Unix
        if os.name == 'nt':
            import string
            drives = [f"{d}:/" for d in string.ascii_uppercase if os.path.exists(f"{d}:/")]
            return {"current_path": "", "folders": [{"name": d, "path": d, "type": "drive"} for d in drives]}
        else:
            path = "/"
    
    # Normalize path and ensure it exists
    path = os.path.abspath(path).replace("\\", "/")
    if not os.path.exists(path):
        return {"error": f"Path does not exist: {path}", "current_path": path}
    
    try:
        items = []
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir():
                    items.append({"name": entry.name, "path": entry.path.replace("\\", "/"), "type": "directory"})
        
        # Sort folders alphabetically
        items.sort(key=lambda x: x["name"].lower())
        return {
            "current_path": path.replace("\\", "/"),
            "parent_path": os.path.dirname(path).replace("\\", "/"),
            "folders": items
        }
    except Exception as e:
        return {"error": str(e), "current_path": path}

@app.get("/explorer/files")
async def explorer_files(root_path: str = Query(..., description="Absolute path to the project root")):
    """Get the file tree for any absolute path."""
    if not os.path.exists(root_path):
        return {"error": "Path not found", "tree": []}
    
    tree = get_directory_tree(root_path, root_path)
    return {"tree": tree, "root_path": root_path}

@app.get("/file")
async def get_file_content(path: str = Query(..., description="Absolute path to the file")):
    """Read content of a file from an absolute path."""
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        return {"error": str(e)}

@app.post("/generate")
async def generate_project(request: ProjectRequest, background_tasks: BackgroundTasks):
    from src.tools.sse_handler import clear_log_history
    clear_log_history()
    background_tasks.add_task(run_workflow, request.task, request.project_name, request.project_dir)
    return {"status": "started", "task": request.task, "project_name": request.project_name}

@app.get("/stream")
async def stream_logs():
    """SSE endpoint — streams log messages from the log_queue to the frontend."""
    return StreamingResponse(log_streamer(), media_type="text/event-stream")



async def run_workflow(task: str, project_name: Optional[str] = None, project_dir: Optional[str] = None):
    logger.info(f"API: Received task - {task}")
    
    if project_dir:
        os.makedirs(project_dir, exist_ok=True)
    elif project_name:
        project_dir = os.path.join(OUTPUT_DIR, project_name)
        os.makedirs(project_dir, exist_ok=True)

    initial_state = ProjectState(
        task=task,
        max_iterations=3,
        project_dir=project_dir
    )
    try:
        await workflow_app.ainvoke(initial_state)
        logger.info("SUCCESS: Project generation complete.")
    except Exception as e:
        logger.error(f"ERROR: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

