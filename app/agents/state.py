from typing import TypedDict, List, Annotated, Any
import operator


class AgentState(TypedDict):
    """using annotated with operator .add ensure that messages are 
        are appened to the history rather than replaced 
    """
    messages: Annotated[List[dict],operator.add ]
    current_query : str
    documents: List[dict[str, Any]]
    plan : List[str]
    status : str
    final_answer: str
