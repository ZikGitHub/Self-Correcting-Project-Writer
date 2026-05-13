import asyncio
import os
from dotenv import load_dotenv
from src.graph.graph import app
from src.graph.state import ProjectState
from src.tools.logger import logger

load_dotenv()

async def run_project_writer(task: str):
    logger.info(f"Starting Project Writer for task: {task}")
    
    initial_state = ProjectState(
        task=task,
        max_iterations=3,
        test_command="pytest" # Default test runner
    )
    
    final_state = await app.ainvoke(initial_state)
    
    print("\n--- GENERATED PROJECT STRUCTURE ---")
    for path in final_state.get("files", {}).keys():
        print(f"  [+] {path}")
        
    if final_state["execution_status"] == "success":
        logger.info(f"Project completed successfully at: {final_state['project_dir']}")
        print(f"\n--- PROJECT CREATED: {final_state['project_dir']} ---")
    else:
        logger.error("Project failed to reach a successful state.")


if __name__ == "__main__":
    import sys
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Create a simple calculator with math operations and unit tests."
    asyncio.run(run_project_writer(task))
