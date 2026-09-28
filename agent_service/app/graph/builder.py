"""Ensambla el StateGraph de LangGraph a partir de nodes.py y edges.py.

retrieve_context -> call_llm -> (tool_call?) -> call_tool -> call_llm -> ...
                                              -> generate_proactive_suggestion -> END
"""

from langgraph.graph import END, StateGraph

from app.graph.edges import should_call_tool
from app.graph.nodes import call_llm, call_tool, generate_proactive_suggestion, retrieve_context
from app.graph.state import AgentState


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("call_llm", call_llm)
    graph.add_node("call_tool", call_tool)
    graph.add_node("generate_proactive_suggestion", generate_proactive_suggestion)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "call_llm")
    graph.add_conditional_edges(
        "call_llm",
        should_call_tool,
        {"call_tool": "call_tool", "generate_proactive_suggestion": "generate_proactive_suggestion"},
    )
    graph.add_edge("call_tool", "call_llm")
    graph.add_edge("generate_proactive_suggestion", END)

    return graph.compile()


agent_graph = build_agent_graph()
