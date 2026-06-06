from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from dk_agent.executor.direct_executor import DirectExecutor
from dk_agent.graph.nodes import (
    make_clarification_node,
    make_execute_node,
    make_meta_node,
    make_response_node,
)
from dk_agent.graph.routing import route_after_meta
from dk_agent.graph.state import AgentGraphState
from dk_agent.routing.meta_controller import MetaController


def build_agent_graph(meta_controller: MetaController, direct_executor: DirectExecutor):
    graph = StateGraph(AgentGraphState)
    graph.add_node("meta", make_meta_node(meta_controller))
    graph.add_node("clarification", make_clarification_node())
    graph.add_node("execute", make_execute_node(direct_executor))
    graph.add_node("response", make_response_node())

    graph.add_edge(START, "meta")
    graph.add_conditional_edges(
        "meta",
        route_after_meta,
        {
            "clarify": "clarification",
            "execute": "execute",
        },
    )
    graph.add_edge("clarification", "response")
    graph.add_edge("execute", "response")
    graph.add_edge("response", END)
    return graph.compile()
