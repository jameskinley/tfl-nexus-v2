# TfL Nexus v2

## API Documentation

> **[📄 REST API Reference (PDF)](../../raw/main/docs/api-docs.pdf)** &nbsp;|&nbsp; **[[REST API]] (Wiki — generated from OpenAPI spec)**

---

A comprehensive Transport for London (TfL) data ingestion, routing, and monitoring system with a REST API, graph-based journey planning, and AI assistant integration via the Model Context Protocol.

---

## Features

| Category | Capability |
|----------|-----------|
| **Data Ingestion** | Full TfL API integration — lines, routes, stations, timetables |
| **REST API** | FastAPI with HATEOAS, async endpoints, and auto-generated docs |
| **Journey Planning** | Graph-based routing with four strategies (fastest, robust, low-crowding, ML hybrid) |
| **Disruption Tracking** | Bayesian reliability scoring from historical disruption data |
| **Crowding Data** | Real-time crowding metrics polled from TfL every 5 minutes |
| **Network Reports** | Automated reports with optional LLM summarization |
| **MCP Server** | AI assistant integration for Claude, GitHub Copilot, and any MCP-compatible client |

---

## Quick Start

### Docker Compose (recommended)

```bash
cp db.env.example db.env   # add your Postgres credentials
docker compose up --build
```

| Service | URL |
|---------|-----|
| REST API | http://localhost:9000 |
| MCP Server | http://localhost:9002/sse |
| PostgreSQL | localhost:9001 |

### Local Python

```bash
pip install -r requirements.txt
python src/init_db.py          # initialise database
python src/app.py              # start REST API + MCP server
curl -X POST http://localhost:9000/route/ingest   # ingest TfL data (~5–10 min)
```

---

## Architecture

```
TfL API → TflClient → API Models → Mapper → DB Models (PostgreSQL)
                                                    ↓
                             FastAPI REST API ← Commands ← Adapters ← MCP Server
```

### Key Components

| Module | Purpose |
|--------|---------|
| `src/app.py` | FastAPI application entry point |
| `src/mcp_provider.py` | FastMCP server (port 9002) |
| `src/data/tfl_client.py` | TfL API client |
| `src/data/mapper.py` | API ↔ DB model conversion |
| `src/graph/routing_strategies.py` | Journey routing algorithms |
| `src/adapters/` | MCP tool implementations |
| `src/tasks/` | Background polling tasks |

---

## Wiki Pages

- [[MCP Docs]] — MCP server setup, tools reference, and example prompts
- [[REST API]] — Full REST API reference (generated from OpenAPI spec)
