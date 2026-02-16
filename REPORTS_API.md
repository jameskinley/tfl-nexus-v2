# Network Reports API Guide

## Overview
The Network Reports API provides full CRUD (Create, Read, Update, Delete) functionality for generating and managing automated network status reports.

## LLM Configuration (Backend)
LLM summarization is now a **backend configuration** rather than a client API option. Configure via environment variables in `.env`:

```bash
# Enable LLM-based summarization
USE_LLM_SUMMARIZER=true
LLM_API_ENDPOINT=https://api.openai.com/v1/completions
LLM_API_KEY=sk-your-api-key-here
```

When `USE_LLM_SUMMARIZER=false` or not set, the system uses simple template-based summarization.

## API Endpoints

### 1. Create Report
**POST** `/reports`

Generate a new network status report.

**Request Body:**
```json
{
  "report_type": "snapshot"
}
```

**Parameters:**
- `report_type` (string, optional): Type of report - `"snapshot"`, `"daily_summary"`, or `"incident"`. Default: `"snapshot"`

**Response:**
```json
{
  "id": 1,
  "timestamp": "2024-01-15T10:30:00",
  "report_type": "snapshot",
  "summary": "Network Status: 2 active disruptions affecting 2 lines...",
  "data": {
    "total_disruptions": 2,
    "active_lines_count": 11,
    "affected_lines_count": 2,
    "line_statuses": {...},
    "graph_metrics": {...},
    "disruption_breakdown": {...}
  }
}
```

### 2. List Reports
**GET** `/reports`

Retrieve a list of network reports with optional filtering.

**Query Parameters:**
- `start_date` (string, optional): ISO format start date filter
- `end_date` (string, optional): ISO format end date filter
- `report_type` (string, optional): Filter by report type
- `limit` (int, optional): Maximum results to return. Default: 50
- `offset` (int, optional): Pagination offset. Default: 0

**Example:**
```bash
# Get all reports
curl http://localhost:8000/reports

# Get reports from the last week
curl "http://localhost:8000/reports?start_date=2024-01-08T00:00:00"

# Get snapshot reports only, limited to 10
curl "http://localhost:8000/reports?report_type=snapshot&limit=10"
```

**Response:**
```json
[
  {
    "id": 1,
    "timestamp": "2024-01-15T10:30:00",
    "report_type": "snapshot",
    "total_disruptions": 2,
    "active_lines_count": 11,
    "affected_lines_count": 2,
    "graph_connectivity_score": 1.0,
    "average_reliability_score": 94.5,
    "summary": "Network Status: 2 active disruptions..."
  },
  ...
]
```

### 3. Get Report Details
**GET** `/reports/{id}`

Retrieve full details for a specific report.

**Example:**
```bash
curl http://localhost:8000/reports/1
```

**Response:**
```json
{
  "id": 1,
  "timestamp": "2024-01-15T10:30:00",
  "report_type": "snapshot",
  "summary": "Network Status: 2 active disruptions affecting 2 lines...",
  "data": {
    "total_disruptions": 2,
    "active_lines_count": 11,
    "affected_lines_count": 2,
    "line_statuses": {
      "Piccadilly": "Minor Delays",
      "Central": "Good Service",
      ...
    },
    "graph_metrics": {
      "nodes": 250,
      "edges": 500,
      "components": 1,
      "density": 0.008
    },
    "disruption_breakdown": {
      "Minor Delays": 1,
      "Severe Delays": 1
    },
    "crowding_summary": {
      "total_records": 42,
      "high_crowding_count": 8,
      "data_age_minutes": 30
    }
  },
  "metadata": {
    "total_disruptions": 2,
    "active_lines_count": 11,
    "affected_lines_count": 2,
    "graph_connectivity_score": 1.0,
    "average_reliability_score": 94.5
  }
}
```

### 4. Update Report (NEW!)
**PUT** `/reports/{id}`

Update an existing report's type or regenerate its summary with current data.

**Request Body:**
```json
{
  "report_type": "incident",
  "regenerate_summary": true
}
```

**Parameters:**
- `report_type` (string, optional): New report type
- `regenerate_summary` (boolean, optional): Whether to recalculate metrics and regenerate summary. Default: `false`

**Use Cases:**
- Change report type without regenerating: Useful for reclassifying historical reports
- Regenerate summary with current data: Useful for updating a report with latest network status
- Both: Reclassify and update with fresh data

**Example:**
```bash
# Just change the report type
curl -X PUT http://localhost:8000/reports/1 \
  -H "Content-Type: application/json" \
  -d '{"report_type": "incident"}'

# Regenerate with current network data
curl -X PUT http://localhost:8000/reports/1 \
  -H "Content-Type: application/json" \
  -d '{"regenerate_summary": true}'

# Both: change type AND regenerate
curl -X PUT http://localhost:8000/reports/1 \
  -H "Content-Type: application/json" \
  -d '{"report_type": "daily_summary", "regenerate_summary": true}'
```

**Response:** Same structure as GET `/reports/{id}` - full updated report details

### 5. Delete Report
**DELETE** `/reports/{id}`

Delete a network report.

**Example:**
```bash
curl -X DELETE http://localhost:8000/reports/1
```

**Response:**
```json
{
  "message": "Report 1 deleted successfully"
}
```

## Background Tasks

The system runs three background tasks automatically:

1. **Disruption Polling** (every 2 minutes): Fetches live disruption data from TfL API
2. **Crowding Polling** (every 5 minutes): Fetches crowding metrics for all lines
3. **Daily Report Generation** (every 24 hours): Automatically generates a `daily_summary` report

## Report Types

- **`snapshot`**: Point-in-time network status
- **`daily_summary`**: Comprehensive daily overview (auto-generated)
- **`incident`**: Focused report during significant disruptions

## LLM Integration Architecture

### Before (Client-side configuration) ❌
```json
// Client had to provide LLM config in every request
{
  "report_type": "snapshot",
  "use_llm": true,
  "llm_api_endpoint": "https://api.openai.com/v1/completions",
  "llm_api_key": "sk-..."
}
```

### After (Backend configuration) ✅
```json
// Client just specifies report type
{
  "report_type": "snapshot"
}
```

Backend reads from `.env`:
```bash
USE_LLM_SUMMARIZER=true
LLM_API_ENDPOINT=https://api.openai.com/v1/completions
LLM_API_KEY=sk-...
```

**Benefits:**
- Security: API keys never exposed to clients
- Consistency: All reports use the same summarization method
- Simplicity: Clients don't manage LLM configuration
- Centralized: Change summarization strategy without updating clients

## Python SDK Example

```python
import requests

BASE_URL = "http://localhost:8000"

# Create a report
response = requests.post(
    f"{BASE_URL}/reports",
    json={"report_type": "snapshot"}
)
report = response.json()
print(f"Created report {report['id']}: {report['summary']}")

# List reports from the last 24 hours
from datetime import datetime, timedelta
start = (datetime.now() - timedelta(days=1)).isoformat()

response = requests.get(
    f"{BASE_URL}/reports",
    params={"start_date": start, "limit": 10}
)
reports = response.json()
print(f"Found {len(reports)} reports in the last 24 hours")

# Get full report details
report_id = reports[0]["id"]
response = requests.get(f"{BASE_URL}/reports/{report_id}")
full_report = response.json()
print(f"Full data: {full_report['data']}")

# Update report - regenerate with current data
response = requests.put(
    f"{BASE_URL}/reports/{report_id}",
    json={"regenerate_summary": True}
)
updated_report = response.json()
print(f"Updated: {updated_report['summary']}")

# Delete report
response = requests.delete(f"{BASE_URL}/reports/{report_id}")
print(response.json()["message"])
```

## Testing

```bash
# Start the server
uvicorn src.app:app --reload

# Create a test report
curl -X POST http://localhost:8000/reports \
  -H "Content-Type: application/json" \
  -d '{"report_type": "snapshot"}'

# View all reports
curl http://localhost:8000/reports

# Get specific report (replace {id} with actual ID)
curl http://localhost:8000/reports/1

# Update report
curl -X PUT http://localhost:8000/reports/1 \
  -H "Content-Type: application/json" \
  -d '{"regenerate_summary": true}'

# Delete report
curl -X DELETE http://localhost:8000/reports/1
```

## Error Responses

**404 Not Found:**
```json
{
  "detail": "Report 999 not found"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Failed to generate report: <error message>"
}
```
