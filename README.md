# TfL Nexus v2

A comprehensive Transport for London (TfL) data ingestion and routing system with SQLAlchemy-based persistence and timetable support.

## Features

- ✅ **Complete TfL API Integration**: Fetch lines, routes, stations, and timetables
- ✅ **SQLAlchemy ORM**: Code-first database with SQLite support (easily switchable to PostgreSQL)
- ✅ **Timetable Support**: Full schedule and timing data for accurate route planning
- ✅ **Mapper Pattern**: Clean separation between API models and database models
- ✅ **FastAPI REST API**: Modern async web framework with automatic documentation
- ✅ **Time-Aware Queries**: Query schedules by time of day for accurate service information

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

### Association Tables
- **station_mode**: Many-to-many Station ↔ Mode
- **station_line**: Many-to-many Station ↔ Line

## Installation

### Prerequisites
- Python 3.10+
- pip

### Setup

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

3. **Start the API server**:
   ```bash
   uvicorn src.app:app --reload
   ```

4. **Ingest TfL data** (runs as background task, takes 5-10 minutes):
   ```bash
   curl -X POST http://localhost:8000/route/ingest
   ```

5. **Check ingestion progress**:
   ```bash
   curl http://localhost:8000/route/ingest/status
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

### Future Endpoints
- `GET /route/{from}/{to}` - Calculate route between stations (TODO)

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Usage Examples

### 1. Ingest Data
```bash
# Initialize and populate database
python src/init_db.py

# Start ingestion (background task)
curl -X POST http://localhost:8000/route/ingest

# Check status
curl http://localhost:8000/route/ingest/status
```

### 2. Query Lines
```bash
# Get all lines
curl http://localhost:8000/line

# Get specific line with routes and timetables
curl http://localhost:8000/line/piccadilly
```

### 3. Check Database Stats
```bash
curl http://localhost:8000/stats
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

## Development

### Project Structure
```
tfl-nexus-v2/
├── data/
│   └── Stops.csv              # NaPTAN lookup data
├── src/
│   ├── app.py                 # FastAPI application
│   ├── init_db.py            # Database initialization script
│   └── data/
│       ├── tfl_client.py     # TfL API client
│       ├── models.py         # API models (Pydantic)
│       ├── db_models.py      # Database models (SQLAlchemy)
│       ├── mapper.py         # Model conversion layer
│       ├── database.py       # Database configuration
│       └── data_ingest.py    # Data ingestion pipeline
├── requirements.txt           # Python dependencies
└── README.md                 # This file
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

### Future Enhancements
- [ ] Implement route calculation using NetworkX
- [ ] Add station coordinates from TfL API
- [ ] Store live disruption data in database
- [ ] Add caching layer (Redis)
- [ ] Implement WebSocket for live updates
- [ ] Add authentication and rate limiting
- [ ] Create admin panel for data management

## License

MIT

## Author

Built for University Year 3 Web Data coursework
