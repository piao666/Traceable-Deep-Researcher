"""Deep Agents x Traceable Deep Researcher example.

Runs Traceable Deep Researcher as the research engine inside a LangChain Deep Agent
harness: the main agent plans with todos, delegates sections to researcher
subagents with isolated context, offloads drafts to a filesystem, and
assembles a final cited report.
"""
