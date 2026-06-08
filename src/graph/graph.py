from langgraph.graph import StateGraph, END
from .state import ProjectState, ExecutionStatus
from .nodes import architect_node, planner_node, generator_node, file_writer_node, validator_node, requirements_node

def validation_router(state: ProjectState):
    # If the validator marked it success, generate requirements then end
    if state.execution_status == ExecutionStatus.SUCCESS:
        return "requirements"
    
    if state.execution_status == ExecutionStatus.FAILURE:
        return "architect"
    
    if state.iteration >= state.max_iterations:
        return "requirements" # Final attempt to generate reqs even if partial success
        
    # Otherwise, loop back to generator to fix the specific failed files
    return "generator"

def create_graph():
    workflow = StateGraph(ProjectState)
    
    workflow.add_node("architect", architect_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("generator", generator_node)
    workflow.add_node("file_writer", file_writer_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("requirements", requirements_node)
    
    workflow.set_entry_point("architect")
    workflow.add_edge("architect", "planner")
    workflow.add_edge("planner", "generator")
    workflow.add_edge("generator", "file_writer")
    workflow.add_edge("file_writer", "validator")
    
    workflow.add_conditional_edges("validator", validation_router)
    workflow.add_edge("requirements", END)
    
    return workflow.compile()

app = create_graph()
