from fastapi import FastAPI
from routers import *
from tasks import lifespan

tags_metadata = [
    {
        "name": "Journeys",
        "description": "Journey planning between stations with multiple optimization strategies. "
                       "Request journey plans as resources using natural semantics."
    },
    {
        "name": "Lines",
        "description": "Transport line information including routes, schedules, and disruption status. "
                       "Access details for tube, overground, DLR, and other TfL lines."
    },
    {
        "name": "Stations",
        "description": "Station search and information including connectivity, crowding, and graph status. "
                       "Query station details and relationships."
    },
    {
        "name": "Disruptions",
        "description": "Service disruption tracking and analysis with historical data. "
                       "Query disruptions across the network with flexible filtering."
    },
    {
        "name": "Reports",
        "description": "Network status reports with AI-powered summaries and historical tracking. "
                       "Generate, retrieve, and manage network health reports."
    },
    {
        "name": "Network",
        "description": "Transport network topology and analysis including graph metrics and visualization. "
                       "Access network-wide crowding information."
    },
    {
        "name": "Data Imports",
        "description": "Data import job management for loading TfL network data. "
                       "Monitor import progress and status."
    },
    {
        "name": "System",
        "description": "System health, statistics, and operational metrics. "
                       "Monitor database state and service availability."
    },
    {
        "name": "Reference Data",
        "description": "Reference data including transport modes and disruption categories. "
                       "Access metadata from TfL API."
    }
]

app = FastAPI(
    title="TfL Nexus API",
    openapi_version="3.0.0",
    description="""
# Transport for London Network Intelligence API

A comprehensive RESTful API for analyzing, routing, and monitoring the Transport for London network 
with real-time disruption tracking, intelligent journey planning, and network health reporting.

## Key Features

* **Intelligent Journey Planning**: True REST resource-based journey queries
* **Real-time Disruptions**: Automatic polling and storage of service disruptions
* **Network Analysis**: Graph-based network analysis and visualization
* **Crowding Information**: Real-time crowding data for stations and lines
* **AI-Powered Reports**: Optional LLM-generated network status summaries
* **HATEOAS Support**: Hypermedia links for API discoverability

## RESTful Design

This API follows REST principles with:
- Resources identified by URLs
- Standard HTTP methods (GET, POST, PUT, DELETE)
- Hypermedia links (HATEOAS) for navigation
- Consistent response formats with metadata
- Proper status codes

## Data Sources

All data is sourced from the official Transport for London (TfL) Unified API.
    """,
    version="2.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan
)

app.include_router(journeys)
app.include_router(lines)
app.include_router(stations)
app.include_router(disruptions)
app.include_router(reports)
app.include_router(network)
app.include_router(data_imports)
app.include_router(system)
app.include_router(modes)