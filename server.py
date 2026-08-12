"""Minimal MCP server exposing two tools over stdio."""
import requests
from mcp.server.mcpserver import MCPServer

import conferences

mcp = MCPServer("demo-server")

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    80: "rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    95: "thunderstorm",
}


@mcp.tool()
def get_weather(city: str) -> str:
    """Look up the current real weather for a city using Open-Meteo."""
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1},
        timeout=10,
    ).json()
    results = geo.get("results")
    if not results:
        return f"no data for {city}"

    place = results[0]
    lat, lon = place["latitude"], place["longitude"]

    forecast = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": lat, "longitude": lon, "current_weather": True},
        timeout=10,
    ).json()
    current = forecast["current_weather"]
    condition = WEATHER_CODES.get(current["weathercode"], "unknown")

    return f"{place['name']}, {place.get('country', '')}: {condition}, {current['temperature']}C"


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


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