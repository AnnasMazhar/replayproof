"""Deterministic sample research agent.

No LLM, no network.  Answers questions by searching local fixture documents
using a simple keyword search tool.  Designed to produce reproducible runs
for demo and testing purposes.
"""

from __future__ import annotations

import json
from typing import Any

# Fixture documents embedded directly so no filesystem path assumptions are needed.
FIXTURE_DOCS: dict[str, str] = {
    "solar_energy.txt": (
        "Solar panels convert sunlight into electricity using photovoltaic cells. "
        "A typical residential solar system produces 4-10 kW of power. "
        "Solar energy is a renewable resource that reduces carbon emissions. "
        "Contact: installations@example.com for quotes."
    ),
    "battery_storage.txt": (
        "Battery storage systems store excess solar energy for later use. "
        "Lithium-ion batteries are the most common type. "
        "A 10 kWh battery can power a home for several hours. "
        "Lead-acid batteries are cheaper but less efficient."
    ),
    "installation_guide.txt": (
        "Solar panel installation requires a licensed electrician. "
        "The process takes 1-3 days depending on system size. "
        "Roof orientation and tilt angle affect energy production. "
        "Most systems are connected to the grid via a net metering agreement."
    ),
}


def search_docs(query: str) -> str:
    """Search fixture documents for lines containing the query string.

    Args:
        query: Keyword or phrase to search for (case-insensitive).

    Returns:
        A JSON string with matched snippets, or a no-results message.
    """
    query_lower = query.lower()
    results: list[dict[str, str]] = []

    for doc_name, content in sorted(FIXTURE_DOCS.items()):
        for sentence in content.split("."):
            sentence = sentence.strip()
            if query_lower in sentence.lower() and sentence:
                results.append({"doc": doc_name, "snippet": sentence})

    if not results:
        return json.dumps({"results": [], "message": "No results found."})
    return json.dumps({"results": results[:3]})  # limit to 3 hits


def research_agent(task: str, tools: dict[str, Any]) -> str:
    """Answer a research question using the search_docs tool.

    The agent performs exactly 2-3 tool calls then synthesises an answer.
    It is fully deterministic: same task always produces same output.

    Args:
        task: The question to answer.
        tools: Tool callables provided by the harness.

    Returns:
        A plain-text answer string.
    """
    search = tools.get("search_docs")
    if search is None:
        return "Error: search_docs tool not available."

    # First search: the full task
    result1 = search(query=task)
    hits1 = json.loads(result1).get("results", [])

    # Second search: narrow by first keyword
    first_word = task.split()[0] if task.split() else task
    result2 = search(query=first_word)
    hits2 = json.loads(result2).get("results", [])

    # Aggregate unique snippets
    seen: set[str] = set()
    snippets: list[str] = []
    for hit in hits1 + hits2:
        s = hit.get("snippet", "")
        if s and s not in seen:
            seen.add(s)
            snippets.append(s)

    if not snippets:
        return f"No relevant information found for: {task}"

    return "Based on the documents: " + " ".join(snippets[:4])


def build_tools() -> dict[str, Any]:
    """Return the tool dict to pass to a Recorder."""
    return {"search_docs": search_docs}


if __name__ == "__main__":
    # Quick smoke-test when run directly.
    from agenteval.record import Recorder

    recorder = Recorder(
        agent=research_agent,
        agent_id="research_agent_v1",
        model="none",
        provider="local",
        started_at="2026-01-01T00:00:00Z",
    )
    run = recorder.record(
        task="How do solar panels work",
        tools=build_tools(),
    )
    print(run.to_jsonl())
