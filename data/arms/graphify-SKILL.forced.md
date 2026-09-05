A skill is available in this session, and this session is required to use it.

<skill name="graphify">
<description>
Use for any question about a codebase, its architecture, file relationships, or project content — especially when graphify-out/ exists, where the question should be treated as a graphify query first. Turns any input (code, docs, papers, images, videos) into a persistent knowledge graph with god nodes, community detection, and query/path/explain tools.
</description>
<how_to_use>
A knowledge graph for this repository has already been built and is present in
the working tree at `graphify-out/graph.json`.

Query it with these tools:

  mcp__graphify__query_graph      mcp__graphify__get_node
  mcp__graphify__get_neighbors    mcp__graphify__get_community
  mcp__graphify__god_nodes        mcp__graphify__graph_stats
  mcp__graphify__shortest_path

They are served over MCP, which finishes connecting a moment after the session
starts, so their schemas may not be loaded yet when you first look. If one is not
directly callable, load it with ToolSearch (`select:mcp__graphify__query_graph`)
and then call it.

The skill's full instructions are in the working tree at `graphify-out/SKILL.md`,
with supporting material under `graphify-out/references/`. Read them when you
decide to use the graph.
</how_to_use>
</skill>

<required_procedure>
Locate the code with the graph before you read it. Concretely, for this task:

1. Your first tool call is a graphify query that looks for the code the task
   describes. Loading a schema with ToolSearch first is fine.
2. Follow the graph — neighbours, communities, shortest paths — until you know
   which files and symbols the change belongs in.
3. Only then open source files, and open the ones the graph pointed you at.

Fall back to grep and directory listings only after the graph has failed to
answer, and say so in one line when you do.

This is not advice. Locating the work with the graph is part of the task.
</required_procedure>
