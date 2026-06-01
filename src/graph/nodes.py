import os
import json
import re
import sys
import subprocess
import uuid
import asyncio
from typing import Dict, List, Any
from langchain_ollama import ChatOllama
from .state import ProjectState, ExecutionStatus
from src.tools.logger import logger

def get_llm(model_key="GENERATOR_MODEL"):
    model = os.environ.get(model_key, "qwen2.5-coder:1.5b")
    base_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    return ChatOllama(model=model, temperature=0.1, base_url=base_url)

def extract_json_list(text: str) -> List[Any]:
    # Remove reasoning/thought tags
    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    
    # Try to find JSON list pattern
    start = clean_text.find("[")
    end = clean_text.rfind("]")
    
    if start != -1 and end != -1:
        json_str = clean_text[start:end+1]
        try:
            return json.loads(json_str)
        except Exception as e:
            # Try cleaning trailing commas
            try:
                cleaned = re.sub(r",\s*([\]}])", r"\1", json_str)
                return json.loads(cleaned)
            except:
                logger.debug(f"JSON Parse Error: {str(e)} for string: {json_str[:100]}...")
                pass
    
    logger.warning(f"Failed to find JSON list in response: {text[:200]}...")
    return []
def sanitize_relative_path(rel_path: str, project_dir: str) -> str:
    """Sanitize the relative path by removing redundant project name prefixes."""
    if not rel_path:
        return ""
        
    rel_path = rel_path.strip("/").replace("\\", "/")
    parts = rel_path.split("/")
    if not parts or not project_dir:
        return rel_path
        
    project_base = os.path.basename(project_dir)
    # E.g. "simple_calculator_123456" -> "simple_calculator"
    raw_project_name = re.sub(r'_\d+$', '', project_base).lower()
    # E.g. "simple_calculator" -> "simplecalculator"
    clean_project_name = raw_project_name.replace("_", "").replace("-", "")
    
    first_part = parts[0].lower().replace("_", "").replace("-", "")
    
    # If the first part of the path is redundant (matches project folder name or task-based project name)
    if first_part == clean_project_name or first_part == project_base.lower().replace("_", "").replace("-", ""):
        if len(parts) > 1:
            return "/".join(parts[1:])
            
    return rel_path

# 1. THE ARCHITECT
async def architect_node(state: ProjectState) -> ProjectState:
    logger.info("Architect: Designing Python system architecture...")
    llm = get_llm("PLANNER_MODEL")
    if not state.project_dir:
        project_id = str(uuid.uuid4())[:8]
        project_dir = os.path.join("output", f"project_{project_id}")
        os.makedirs(project_dir, exist_ok=True)
        state.project_dir = project_dir

    prompt = (
        "You are a Senior Python Architect.\n"
        f"Task: {state.task}\n\n"
        "Instructions:\n"
        "1. Design a modular and professional Python project structure.\n"
        "2. Break it down into high-level directory packages (e.g., src/api, src/core, src/utils, tests). Do NOT include individual file names or '.py' files in the module list; these should strictly represent directory paths.\n"
        "3. Do NOT include the project name, root directory, or any redundant top-level directory prefix in the module paths. The paths must be relative and start directly with standard relative directories like 'src/', 'tests/', etc. without prepending any project folder names.\n"
        "4. Respond ONLY with a JSON list of modules in this format:\n"
        "[{\"module\": \"path/to/module\", \"description\": \"brief purpose\"}]\n\n"
        "JSON List:"
    )
    response = await llm.ainvoke(prompt)
    state.modules = extract_json_list(response.content)
    
    if not state.modules:
        logger.warning(f"Architect: Failed to generate structure. Raw response preview: {response.content[:100]}...")
        state.modules = [{"module": "src/core", "description": "Main business logic"}]

    sanitized_modules = []
    for mod in state.modules:
        if isinstance(mod, dict):
            name = mod.get("module") or mod.get("name")
            if name:
                sanitized_name = sanitize_relative_path(name, state.project_dir)
                # If the module path ends in .py, strip the file part to ensure we only create directories
                if sanitized_name.endswith(".py"):
                    sanitized_name = os.path.dirname(sanitized_name)
                
                if sanitized_name:
                    mod["module"] = sanitized_name
                    sanitized_modules.append(mod)
                    os.makedirs(os.path.join(state.project_dir, sanitized_name), exist_ok=True)
        else:
            sanitized_name = sanitize_relative_path(str(mod), state.project_dir)
            if sanitized_name.endswith(".py"):
                sanitized_name = os.path.dirname(sanitized_name)
            
            if sanitized_name:
                sanitized_modules.append(sanitized_name)
                os.makedirs(os.path.join(state.project_dir, sanitized_name), exist_ok=True)
            
    state.modules = sanitized_modules
    return state

# 2. THE DETAILED PLANNER
async def planner_node(state: ProjectState) -> ProjectState:
    logger.info(f"Planner: Expanding {len(state.modules)} modules into files...")
    llm = get_llm("PLANNER_MODEL")
    all_files = []
    for mod in state.modules:
        module_name = mod.get("module") or mod.get("name") if isinstance(mod, dict) else mod
        if not module_name:
            logger.warning(f"Planner: Skipping invalid module: {mod}")
            continue

        prompt = (
            "You are a Python Lead Developer.\n"
            f"Project Task: {state.task}\n"
            f"Current Module: {module_name}\n\n"
            "Instructions:\n"
            "1. List the specific .py files required for this module.\n"
            "2. Include necessary __init__.py files.\n"
            "3. Ensure all file paths are relative and do NOT include any redundant project name or root folder prefixes. Each path must be relative to the module folder, e.g. 'filename.py' or 'subfolder/filename.py'.\n"
            "4. Respond ONLY with a JSON list in this format:\n"
            "[{\"path\": \"filename.py\", \"purpose\": \"brief purpose\"}]\n\n"
            "JSON List:"
        )
        response = await llm.ainvoke(prompt)
        files = extract_json_list(response.content)
        
        if not files:
            logger.warning(f"Planner: No files suggested for {module_name}. Raw response preview: {response.content[:100]}...")
            files = [{"path": "logic.py", "purpose": "Core implementation"}]

        for file_info in files:
            if not isinstance(file_info, dict): continue
            path = file_info.get("path", "").strip("/")
            if not path or not path.endswith(".py"): path += ".py"
            
            clean_module_name = module_name.strip("/")
            
            # Smart join: detect if the file path overlaps with the end of the module path.
            # E.g. module="src/api", path="api/addition.py" -> overlap on "api" -> "src/api/addition.py"
            # E.g. module="src/core", path="addition.py" -> no overlap -> "src/core/addition.py"
            # E.g. module="src/api", path="src/api/addition.py" -> full prefix match -> "src/api/addition.py"
            if path.startswith(clean_module_name + "/") or path == clean_module_name:
                # Path already includes full module prefix
                pass
            else:
                # Check for overlapping suffix of module with prefix of path
                module_parts = clean_module_name.split("/")
                path_parts = path.split("/")
                merged = False
                # Try progressively shorter suffixes of the module path
                for i in range(1, len(module_parts) + 1):
                    suffix = "/".join(module_parts[i:])  # e.g. "api" when module is "src/api" and i=1
                    if suffix and path.startswith(suffix + "/"):
                        # Found overlap: use module prefix + remainder after the overlapping part
                        prefix = "/".join(module_parts[:i])  # e.g. "src"
                        path = prefix + "/" + path  # e.g. "src/api/addition.py"
                        merged = True
                        break
                if not merged:
                    path = os.path.join(clean_module_name, path).replace("\\", "/")
            
            # Sanitize combined file path to strip any redundant project name prefix
            sanitized_path = sanitize_relative_path(path, state.project_dir)
            file_info["path"] = sanitized_path
            all_files.append(file_info)
    
    state.plan = all_files
    return state

# 3. PARALLEL GENERATOR WORKER
async def process_file_worker(file_info: Dict[str, str], state: ProjectState, context: str = ""):
    path = file_info.get("path")
    purpose = file_info.get("purpose")
    full_path = os.path.join(state.project_dir, path)
    
    if path.endswith("__init__.py"):
        llm = ChatOllama(model="qwen2.5-coder:0.5b", temperature=0.1, base_url=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    else:
        llm = get_llm("GENERATOR_MODEL")
        
    attempts = 0
    max_attempts = 2
    success = False
    error = ""
    code = ""

    while attempts < max_attempts and not success:
        prompt = (
            f"Overall Task: {state.task}\n"
            f"File: {path}\n"
            f"Purpose: {purpose}\n\n"
            f"--- EXISTING CODEBASE CONTEXT ---\n{context}\n\n"
            "Generate complete Python 3 code. Output ONLY code inside backticks."
        )
        if error: prompt += f"\n\nFIX PREVIOUS ERROR: {error}"

        response = await llm.ainvoke(prompt)
        clean_content = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip()
        code_match = re.search(r"```(?:python|txt)?\n?(.*?)\n?```", clean_content, re.DOTALL)
        code = code_match.group(1).strip() if code_match else clean_content.strip()

        if len(code) < 50:
            error = "Code is too short. Provide full implementation."
            attempts += 1
            continue

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f: f.write(code)

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = state.project_dir + os.pathsep + env.get("PYTHONPATH", "")
            result = subprocess.run([sys.executable, full_path], capture_output=True, text=True, timeout=5, env=env)
            if result.returncode == 0:
                success = True
            else:
                error = result.stderr
                attempts += 1
        except:
            attempts += 1
            
    return path, code

async def generator_node(state: ProjectState) -> ProjectState:
    # Build a context summary from already written files
    context_summary = ""
    for path, code in state.files.items():
        context_summary += f"\n# --- File: {path} ---\n{code}\n"

    if state.iteration == 0:
        logger.info(f"Generator: PASS 1 (Parallel Draft) for {len(state.plan)} files...")
        if not state.plan:
             return state
        tasks = [process_file_worker(file_info, state, context_summary) for file_info in state.plan]
        results = await asyncio.gather(*tasks)
        for path, code in results: state.files[path] = code
    else:
        logger.info(f"Generator: PASS {state.iteration + 1} (Sequential Polish) for {len(state.plan)} files...")
        for file_info in state.plan:
            path, code = await process_file_worker(file_info, state, context_summary)
            state.files[path] = code
            context_summary += f"\n# --- File: {path} ---\n{code}\n"
        
    return state

# 4. FILE WRITER
async def file_writer_node(state: ProjectState) -> ProjectState:
    logger.info("File Writer: Finalizing files...")
    for path, code in state.files.items():
        full_path = os.path.join(state.project_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f: f.write(code)
    return state

# 5. VALIDATOR
async def validator_node(state: ProjectState) -> ProjectState:
    logger.info("Validator: Auditing project content...")
    
    # 1. Reject Empty Projects
    if not state.files:
        logger.error("Validator: FAILURE - Zero files generated. Routing back to Architect.")
        state.execution_status = ExecutionStatus.FAILURE
        state.iteration += 1
        return state

    # 2. Check for stubs
    failed_files = []
    for path, code in state.files.items():
        if len(code) < 100 or "Placeholder" in code:
            logger.warning(f"Validator: Found stub file: {path}")
            purpose = next((p["purpose"] for p in state.plan if p["path"] == path), "Implementation")
            failed_files.append({"path": path, "purpose": purpose})

    if failed_files and state.iteration < 3:
        logger.info(f"Validator: {len(failed_files)} files need polish. Looping back...")
        state.plan = failed_files
        state.execution_status = ExecutionStatus.PENDING
    else:
        logger.info("Validator: Project verified successfully.")
        state.execution_status = ExecutionStatus.SUCCESS
        
    state.iteration += 1
    return state
