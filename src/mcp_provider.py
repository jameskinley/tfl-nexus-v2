from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
        "tfl-nexus-v2", 
        "TfL Nexus API provides real-time transport data for London, including disruptions, crowding levels, and journey planning. " \
        "It serves as an alternative route planner and disruption monitor. ",
        port=9002,
        host="0.0.0.0"
        )