"""Minimal MCP server exposing two tools over stdio."""
from mcp.server.mcpserver import MCPServer

import conferences

mcp = MCPServer("demo-server")

@mcp.tool()
def list_upcoming_conferences(category: str, limit: int = 20) -> list[dict]:
    """List upcoming conference deadlines for a field.

    category: 'ai', 'ml', 'security', 'database', 'network', 'software',
    'hci', 'graphics', 'theory', 'data-science', or 'multimedia'.
    Sorted by nearest submission deadline first. Data from ccf-deadlines.
    """
    return conferences.list_upcoming_conferences(category, limit)


@mcp.tool()
def get_conference_details(acronym: str, category: str) -> dict:
    """Get full deadline history and details for one conference.

    acronym: e.g. 'nips', 'icml', 'ccs', 'sp' (case-insensitive).
    category: same values as list_upcoming_conferences.
    """
    return conferences.get_conference_details(acronym, category)


@mcp.tool()
def search_papers(topic: str, max_results: int = 10) -> list[dict]:
    """Search arXiv for recent papers on a topic, newest first."""
    return conferences.search_papers(topic, max_results)


if __name__ == "__main__":
    mcp.run(transport="stdio")