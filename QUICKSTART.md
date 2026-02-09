# Quick Start Guide - TfL Nexus v2

## 🚀 Get Started in 3 Steps

### 1. Initialize Database
```bash
python src/init_db.py
```

This will **drop all existing tables** and recreate them (fresh start).

Expected output:
```
INFO - Dropping all existing tables...
INFO - All tables dropped
INFO - Creating database tables...
INFO - Database initialized successfully
✅ Database initialized successfully!
Database location: sqlite:///tfl_nexus.db
```

To keep existing data (only create missing tables):
```bash
python src/init_db.py --no-drop
```

### 2. Start API Server
```bash
uvicorn src.app:app --reload
```

Server will start at: http://localhost:8000

### 3. Ingest Data from TfL API
Open a new terminal and run:
```bash
curl -X POST http://localhost:8000/route/ingest
```

This starts the ingestion as a **background task** to prevent timeouts.

⚠️ **Note**: This will take 5-10 minutes. Check progress with:
```bash
curl http://localhost:8000/route/ingest/status
```

The ingestion fetches:
- All tube lines
- All routes for each line
- Timetable data for each route
- Station information

**Progress tracking**: Server terminal shows tqdm progress bars for:
- Line processing
- Route processing  
- Timetable fetching

## 📊 Check Your Data

### View Database Stats
```bash
curl http://localhost:8000/stats
```

Expected response:
```json
{
  "lines": 11,
  "routes": 42,
  "stations": 270,
  "schedules": 84
}
```

### List All Lines
```bash
curl http://localhost:8000/line
```

### Get Specific Line Details
```bash
curl http://localhost:8000/line/piccadilly
```

This returns the line with all routes and timetable information.

## 🌐 API Documentation

Once running, visit these URLs in your browser:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔧 Troubleshooting

### Need a Fresh Start?
The init script always clears the database by default:
```bash
python src/init_db.py
```

### Keep Existing Data?
Add the `--no-drop` flag:
```bash
python src/init_db.py --no-drop
```

### Check What Tables Will Be Created
```bash
python src/init_db.py --show-tables
```

### Port 8000 Already in Use?
Use a different port:
```bash
uvicorn src.app:app --reload --port 8001
```

## 📁 Database Location

The SQLite database is created at: `tfl_nexus.db` in the project root.

You can view it with:
- [DB Browser for SQLite](https://sqlitebrowser.org/)
- VS Code SQLite extension
- Python: `sqlite3 tfl_nexus.db`

## 🔍 Example Queries

### Python - Query Schedules
```python
from src.data.database import get_db_session
from src.data import db_models

with get_db_session() as session:
    # Get all lines
    lines = session.query(db_models.Line).all()
    
    # Get a specific line with routes
    line = session.query(db_models.Line).filter_by(id="piccadilly").first()
    
    # Get all schedules for a route
    route = line.routes[0]
    for schedule in route.schedules:
        print(f"{schedule.name}: {schedule.first_journey_time} - {schedule.last_journey_time}")
        
    # Find active services at 9:00 AM
    current_time = 9 * 60  # minutes from midnight
    periods = session.query(db_models.Period).filter(
        db_models.Period.from_time <= current_time,
        db_models.Period.to_time >= current_time
    ).all()
```

## 🎯 Next Steps

1. **Implement Route Finding**: Use NetworkX to build a graph and calculate routes
2. **Add Caching**: Cache frequently accessed routes
3. **Live Updates**: Integrate real-time disruption data
4. **Frontend**: Build a web UI for route planning

## 📝 Notes

- First data ingest will be slow but subsequent queries are fast
- Timetable data is extensive - expect ~1-2 MB database
- All times are stored as minutes from midnight for easy querying
- Station intervals include travel time from route origin
