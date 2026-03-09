# TfL Nexus v2

A comprehensive Transport for London (TfL) data ingestion and routing system with SQLAlchemy-based persistence and timetable support.

## Features

- ✅ **Complete TfL API Integration**: Fetch lines, routes, stations, and timetables
- ✅ **SQLAlchemy ORM**: Code-first database with PostgreSQL support (SQLite also supported)
- ✅ **Timetable Support**: Full schedule and timing data for accurate route planning
- ✅ **Mapper Pattern**: Clean separation between API models and database models
- ✅ **FastAPI REST API**: Modern async web framework with automatic documentation
- ✅ **Time-Aware Queries**: Query schedules by time of day for accurate service information
- ✅ **Intelligent Routing**: Multiple routing strategies (fastest, robust, low-crowding, ML hybrid)
- ✅ **Disruption Analysis**: Bayesian-based reliability scoring from historical disruptions
- ✅ **Network Reports**: Automated report generation with optional LLM summarization
- ✅ **Crowding Data**: Real-time crowding metrics from TfL API
- ✅ **MCP Server**: AI assistant integration via the Model Context Protocol (port 9002)

## Architecture

### Data Flow
```
TfL API → TflClient → API Models (models.py) → Mapper → DB Models (db_models.py) → SQLite
```

### Key Components

1. **[src/data/models.py](src/data/models.py)**: API/response models (Pydantic)
2. **[src/data/db_models.py](src/data/db_models.py)**: Database models (SQLAlchemy)
3. **[src/data/mapper.py](src/data/mapper.py)**: Bidirectional conversion between API ↔ DB models
4. **[src/data/tfl_client.py](src/data/tfl_client.py)**: TfL API client with timetable parsing
5. **[src/data/database.py](src/data/database.py)**: Database configuration and session management
6. **[src/data/data_ingest.py](src/data/data_ingest.py)**: Data ingestion orchestration
7. **[src/app.py](src/app.py)**: FastAPI application with REST endpoints
8. **[src/mcp_provider.py](src/mcp_provider.py)**: FastMCP server instance (port 9002)
9. **[src/adapters/](src/adapters/)**: MCP tool implementations wrapping core commands

## Database Schema

### Core Tables
- **modes**: Transport modes (tube, bus, etc.)
- **lines**: Transit lines (e.g., Piccadilly Line)
- **routes**: Directional routes for each line
- **stations**: Physical stations with coordinates
- **station_naptans**: NaPTAN codes for stations (one-to-many)

### Timetable Tables
- **station_intervals**: Stop sequences with travel times
- **schedules**: Service schedules (weekday, weekend, etc.)
- **periods**: Frequency periods (e.g., peak hours: 3-5 min frequency)
- **known_journeys**: Specific scheduled departure times

### Disruption & Analysis Tables
- **disruptions**: Network disruptions with historical tracking
- **disruption_events**: Event log for disruption state changes
- **station_crowding**: Real-time crowding metrics per station/line
- **network_reports**: Automated network status reports

### Association Tables
- **station_mode**: Many-to-many Station ↔ Mode
- **station_line**: Many-to-many Station ↔ Line

## Installation

### Prerequisites
- Python 3.10+
- pip

### Setup

#### Option A — Docker Compose (recommended)

```bash
cp db.env.example db.env   # configure Postgres credentials
docker compose up --build
```

Services started:
- REST API → http://localhost:9000
- MCP Server → http://localhost:9002/sse
- PostgreSQL → localhost:9001

#### Option B — Local Python

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize database** (drops all existing tables and recreates):
   ```bash
   python src/init_db.py
   ```
   
   To keep existing data:
   ```bash
   python src/init_db.py --no-drop
   ```

3. **Start the API + MCP server**:
   ```bash
   python src/app.py
   ```
   This starts both the REST API (port 9000) and the MCP server (port 9002) together.

4. **Ingest TfL data** (runs as background task, takes 5-10 minutes):
   ```bash
   curl -X POST http://localhost:9000/route/ingest
   ```

5. **Check ingestion progress**:
   ```bash
   curl http://localhost:9000/route/ingest/status
   ```

## API Endpoints

### Data Management
- `POST /route/ingest` - Start TfL data ingestion as background task (prevents timeout)
- `GET /route/ingest/status` - Check ingestion progress and status
- `GET /stats` - Database statistics
- `GET /graph/stats` - Graph statistics (nodes, edges, connectivity)

### Query Endpoints
- `GET /line` - List all lines
- `GET /line/{line_id}` - Get line details with routes and timetables
- `GET /line/{line_id}/live-disruptions` - Get live disruption info
- `GET /meta/modes` - List transport modes
- `GET /meta/disruption-categories` - List disruption categories

### Routing Endpoints
- `GET /routes/{from_station}/{to_station}` - Calculate route between stations
  - Query params: `mode` (fastest/robust/low_crowding/ml_hybrid), `alternatives` (number of alternatives)
- `GET /routes/strategies` - List available routing strategies

### Network Reports (CRUD)
- `POST /reports` - Create a new network report
- `GET /reports` - List all reports (with filtering and pagination)
- `GET /reports/{id}` - Get a specific report with full details
- `PUT /reports/{id}` - Update an existing report
- `DELETE /reports/{id}` - Delete a report

### Future Endpoints
- `GET /route/{from}/{to}` - Calculate route between stations (TODO)

## MCP Server (AI Assistant Integration)

TfL Nexus includes an **MCP (Model Context Protocol)** server that lets AI assistants (Claude, GitHub Copilot, etc.) call live TfL data tools directly.

The MCP server runs on **port 9002** (SSE transport) alongside the REST API.

### Available Tools

| Tool | Description |
|------|-------------|
| `plan_route` | Calculate the best route between two stations with configurable strategy |
| `get_network_crowding` | Retrieve live crowding heatmap across all monitored stations |
| `generate_network_report` | Generate and persist a network status report |

### Quick Connect

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "tfl-nexus": { "url": "http://localhost:9002/sse" }
  }
}
```

**VS Code / GitHub Copilot** — add to `.vscode/mcp.json`:
```json
{
  "servers": {
    "tfl-nexus": { "type": "sse", "url": "http://localhost:9002/sse" }
  }
}
```

See [docs/MCP_TOOLS.md](docs/MCP_TOOLS.md) for full parameter reference, example responses, and environment variable configuration.

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:9000/docs
- **ReDoc**: http://localhost:9000/redoc

## Usage Examples

### 1. Ingest Data
```bash
# Initialize and populate database
python src/init_db.py

# Start ingestion (background task)
curl -X POST http://localhost:9000/route/ingest

# Check status
curl http://localhost:9000/route/ingest/status
```

### 2. Query Lines
```bash
# Get all lines
curl http://localhost:9000/line

# Get specific line with routes and timetables
curl http://localhost:9000/line/piccadilly
```

### 3. Check Database Stats
```bash
curl http://localhost:9000/stats
```

### 4. Query Schedules (Python example)
```python
from src.data.database import get_db_session
from src.data import db_models

with get_db_session() as session:
    # Find schedules active at 9:00 AM (540 minutes from midnight)
    current_time = 9 * 60  # 9:00 AM
    
    periods = session.query(db_models.Period).filter(
        db_models.Period.from_time <= current_time,
        db_models.Period.to_time >= current_time
    ).all()
    
    for period in periods:
        print(f"Active service: {period.schedule.name}")
        print(f"Frequency: {period.frequency_min}-{period.frequency_max} minutes")
```

## Configuration

### Database
By default, uses SQLite with file `tfl_nexus.db` in the project root.

To use PostgreSQL:
```bash
export DATABASE_URL="postgresql://user:password@localhost/tflnexus"
python src/init_db.py  # Automatically drops and recreates tables
```

### Environment Variables
- `DATABASE_URL`: Database connection string (default: `sqlite:///tfl_nexus.db`)
- `TFL_API_KEY`: TfL API key (optional, for rate limits)
- `TFL_APP_ID`: TfL Application ID (optional)
- `USE_LLM_SUMMARIZER`: Set to `true` to enable LLM-based report summaries (default: `false`)
- `LLM_API_ENDPOINT`: LLM API endpoint URL (required if USE_LLM_SUMMARIZER=true)
- `LLM_API_KEY`: LLM API key (required if USE_LLM_SUMMARIZER=true)

### Configuration File
Copy `.env.example` to `.env` and configure your settings:
```bash
cp .env.example .env
# Edit .env with your API keys and preferences
```

## Development

### Project Structure
```
tfl-nexus-v2/
├── docs/
│   ├── openapi.json           # OpenAPI specification
│   └── MCP_TOOLS.md          # MCP tool reference documentation
├── src/
│   ├── app.py                 # FastAPI + MCP server entrypoint
│   ├── app_provider.py        # FastAPI app factory
│   ├── mcp_provider.py        # FastMCP server instance
│   ├── init_db.py             # Database initialisation script
│   ├── adapters/              # MCP tool implementations
│   │   ├── journeys_adapter.py   # plan_route tool
│   │   ├── network_adapter.py    # get_network_crowding tool
│   │   └── reports_adapter.py    # generate_network_report tool
│   ├── commands/              # Business logic command layer
│   ├── data/
│   │   ├── tfl_client.py     # TfL API client
│   │   ├── models.py         # API models (Pydantic)
│   │   ├── api_models.py     # Shared API response models
│   │   ├── db_models.py      # Database models (SQLAlchemy)
│   │   ├── mapper.py         # Model conversion layer
│   │   ├── database.py       # Database configuration
│   │   └── data_ingest.py    # Data ingestion pipeline
│   ├── graph/                 # Graph-based routing engine
│   ├── llm/                   # LLM integration (OpenRouter)
│   ├── routers/               # FastAPI route handlers
│   └── tasks/                 # Background tasks (crowding, disruptions)
├── tests/                     # Pytest test suite
├── compose.yaml               # Docker Compose configuration
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

### Reset Database
The init script clears the database by default:
```bash
python src/init_db.py
```

To keep existing data:
```bash
python src/init_db.py --no-drop
```

### Show Tables
```bash
python src/init_db.py --show-tables
```

## Implementation Details

### Mapper Pattern
The system uses a **Data Transfer Object (DTO)** pattern to separate API concerns from database concerns:

- **API Models** (`models.py`): Optimized for JSON serialization and API responses
- **DB Models** (`db_models.py`): Optimized for relational storage and querying
- **Mapper** (`mapper.py`): Handles bidirectional conversion

This allows:
- Clean API responses without database internals
- Efficient database queries with proper relationships
- Easy migration between different data sources

### Timetable Data
Timetables are stored in a normalized structure:

1. **Schedules**: Named service patterns (e.g., "Monday-Friday")
2. **Periods**: Time ranges with service frequencies (e.g., 7:00-9:30, every 3-5 minutes)
3. **Known Journeys**: Specific departure times for non-frequency services
4. **Station Intervals**: Travel time from route origin to each stop

This enables:
- Time-based queries ("What's the service frequency at 8:30 AM?")
- Journey planning with accurate timing
- Support for both scheduled and frequency-based services

### Intelligent Routing Strategies
The system supports multiple routing modes to optimize for different user preferences:

1. **Fastest Route** (`fastest`): Minimizes total journey time
2. **Robust Route** (`robust`): Balances speed with disruption probability using Bayesian analysis
3. **Low Crowding** (`low_crowding`): Avoids heavily crowded stations and lines
4. **ML Hybrid** (`ml_hybrid`): Weighted combination of all factors (time, reliability, crowding)

#### Disruption Analysis
The system uses **Bayesian inference** to predict edge fragility:
- Prior reliability: 95% (assumed base reliability)
- Posterior reliability: Updated based on historical disruption frequency
- Output: Fragility scores per line and station for weighted routing

#### Crowding Integration
Real-time crowding data from TfL API is periodically polled and integrated into routing:
- Crowding levels: low, medium, high, very_high
- Applied as penalties in `low_crowding` and `ml_hybrid` strategies
- Background polling every 5 minutes

### Network Reports
Automated network status reports generated daily (or on-demand):
- Disruption counts and breakdown by category
- Line status summary
- Graph connectivity metrics
- Reliability scores
- Crowding summary

Reports support **pluggable summarizers**:
- **Simple Template**: Rule-based text generation
- **LLM Integration**: Optional AI-powered summaries (configured via backend environment variables)

### Future Enhancements
- [x] Implement route calculation using NetworkX
- [x] Store live disruption data in database
- [x] Add intelligent routing with multiple strategies
- [x] Implement disruption analysis and prediction
- [x] Network reports with LLM integration support
- [ ] Add station coordinates from TfL API
- [ ] Add caching layer (Redis)
- [ ] Implement WebSocket for live updates
- [ ] Add authentication and rate limiting
- [ ] Create admin panel for data management

## License

MIT

## Author

Built for University Year 3 Web Data coursework
