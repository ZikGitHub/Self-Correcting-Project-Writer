from langgraph.graph import StateGraph, END
from .state import ProjectState, ExecutionStatus
from .nodes import architect_node, planner_node, generator_node, file_writer_node, validator_node

def validation_router(state: ProjectState):
    # If the validator marked it success or we hit max iterations, end it
    if state.execution_status == ExecutionStatus.SUCCESS:
        return END
    
    if state.execution_status == ExecutionStatus.FAILURE:
        return "architect"
    
    if state.iteration >= state.max_iterations:
        return END
        
    # Otherwise, loop back to generator to fix the specific failed files
    return "generator"

def create_graph():
    workflow = StateGraph(ProjectState)
    
    workflow.add_node("architect", architect_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("generator", generator_node)
    workflow.add_node("file_writer", file_writer_node)
    workflow.add_node("validator", validator_node)
    
    workflow.set_entry_point("architect")
    workflow.add_edge("architect", "planner")
    workflow.add_edge("planner", "generator")
    workflow.add_edge("generator", "file_writer")
    workflow.add_edge("file_writer", "validator")
    
    workflow.add_conditional_edges("validator", validation_router)
    
    return workflow.compile()

app = create_graph()
