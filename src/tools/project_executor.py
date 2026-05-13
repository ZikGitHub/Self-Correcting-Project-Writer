import os
import subprocess
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any
from .logger import logger

class ProjectExecutor:
    def __init__(self, workspace_root: str = "workspaces"):
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(exist_ok=True)

    def run_project(self, files: Dict[str, str], test_command: str = "pytest") -> Dict[str, Any]:
        """
        Executes a project in a sandboxed directory.
        """
        project_id = f"run_{uuid.uuid4().hex[:6]}"
        run_dir = self.workspace_root / project_id
        run_dir.mkdir()

        try:
            # 1. Write files
            for path, content in files.items():
                file_path = run_dir / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # 2. Setup Environment
            env = os.environ.copy()
            env["PYTHONPATH"] = str(run_dir) + os.pathsep + env.get("PYTHONPATH", "")

            # 3. Execute
            logger.info(f"Running tests in {run_dir} using '{test_command}'")
            result = subprocess.run(
                test_command,
                shell=True,
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "run_dir": str(run_dir)
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "Timeout",
                "error": "The test execution timed out after 60 seconds.",
                "run_dir": str(run_dir)
            }
        except Exception as e:
            logger.error(f"Executor error: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "run_dir": str(run_dir)
            }

executor = ProjectExecutor()
