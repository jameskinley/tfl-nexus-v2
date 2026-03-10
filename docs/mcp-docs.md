# TfL Nexus — MCP Tools Reference

## What is MCP?

The **Model Context Protocol (MCP)** is an open standard developed by Anthropic that allows AI assistants (such as Claude, GitHub Copilot, or any MCP-compatible client) to connect directly to external services and data sources. Rather than relying on a human to copy-paste results or manually relay information, an AI agent equipped with an MCP client can call tools on an MCP server to retrieve live data and take actions autonomously.

TfL Nexus exposes an MCP server alongside its REST API. This lets an AI assistant answer questions like "How do I get from King's Cross to Waterloo right now?" or "Is the network heavily disrupted today?" by calling the appropriate tool and reasoning over the live response — all without any human intermediation.

---

## Server Details

| Property | Value |
|----------|-------|
| Server name | `tfl-nexus-v2` |
| Transport | SSE (Server-Sent Events) |
| Host | `0.0.0.0` |
| Port | `9002` |
| SSE endpoint | `http://localhost:9002/sse` |

The MCP server starts automatically as a background daemon thread when the main application is launched (see [src/app.py](../src/app.py)).

### Docker / Compose

When running via Docker Compose, port `9002` is mapped to the host:

```yaml
ports:
  - "9000:9000"   # REST API
  - "9002:9002"   # MCP server
```

---

## Connecting an MCP Client

### Claude Desktop

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tfl-nexus": {
      "url": "http://localhost:9002/sse"
    }
  }
}
```

### VS Code (GitHub Copilot)

Add to your `.vscode/mcp.json` workspace configuration:

```json
{
  "servers": {
    "tfl-nexus": {
      "type": "sse",
      "url": "http://localhost:9002/sse"
    }
  }
}
```

---

## Tools

There are three tools exposed by the MCP server, implemented in [`src/adapters/`](../src/adapters/).

---

### `plan_route`

**File:** [src/adapters/journeys_adapter.py](../src/adapters/journeys_adapter.py)

Calculates the best route between two London stations. Station names are **fuzzy matched** against the database, so minor misspellings or informal names (e.g. "Kings Cross" instead of "King's Cross St. Pancras") are handled gracefully.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `origin` | `string` | Yes | — | Name or partial name of the departure station |
| `destination` | `string` | Yes | — | Name or partial name of the arrival station |
| `time` | `string` | No | Current time | Desired departure time in `HH:MM` format (24-hour) |
| `strategy` | `string` | No | `"fastest"` | Routing strategy — see [Routing Strategies](#routing-strategies) |
| `alternatives` | `boolean` | No | `false` | Whether to return alternative routes |
| `max_changes` | `integer` | No | `null` | Maximum number of line changes permitted |
| `accessible` | `boolean` | No | `false` | Whether to restrict to step-free accessible routes |
| `avoid_lines` | `string` | No | `null` | Comma-separated list of line IDs to exclude (e.g. `"central,jubilee"`) |

#### Routing Strategies

| Strategy | Description |
|----------|-------------|
| `fastest` | Minimises total journey time using base travel-time weights |
| `robust` | Balances speed against disruption risk using Bayesian reliability scoring |
| `low_crowding` | Penalises crowded stations and lines to produce a more comfortable journey |
| `ml_hybrid` | Weighted combination of time, reliability, and crowding for an all-round optimal route |

#### Response

Returns a `ResourceResponse<JourneyData>` object.

```jsonc
{
  "data": {
    "origin": {
      "id": "940GZZLUKSX",
      "name": "King's Cross St. Pancras Underground Station",
      "lat": 51.5309,
      "lon": -0.1233,
      "modes": ["tube"]
    },
    "destination": {
      "id": "940GZZLUWLO",
      "name": "Waterloo Underground Station",
      "lat": 51.5036,
      "lon": -0.1143,
      "modes": ["tube"]
    },
    "requested_time": "09:00",
    "strategy": "fastest",
    "primary_route": {
      "total_time_minutes": 18.5,
      "total_stops": 6,
      "changes": 1,
      "has_disruptions": false,
      "disruption_warnings": [],
      "segments": [
        {
          "station": { "id": "940GZZLUKSX", "name": "King's Cross St. Pancras Underground Station", "modes": [] },
          "line": "victoria",
          "arrival_time": null,
          "departure_time": null,
          "wait_time_minutes": 3.0
        }
        // ...additional stops
      ]
    },
    "alternatives": []
  },
  "links": {
    "self": { "href": "/journeys/940GZZLUKSX/to/940GZZLUWLO?time=09:00&strategy=fastest", "method": "GET" }
  }
}
```

#### Example Prompt

> "Plan the fastest route from Paddington to London Bridge, avoiding the District line, with no more than 2 changes."

---

### `get_network_crowding`

**File:** [src/adapters/network_adapter.py](../src/adapters/network_adapter.py)

Retrieves the latest crowding heatmap across all monitored stations. This data is sourced from the TfL API and polled periodically in the background (every 5 minutes). **No input parameters are needed or accepted.**

#### Parameters

_None_

#### Response

Returns a `CollectionResponse<CrowdingData>` object — a paginated list of crowding entries, one per station.

```jsonc
{
  "data": [
    {
      "station_id": "940GZZLURGP",
      "line_id": null,
      "crowding_level": null,
      "capacity_percentage": 0.72,
      "timestamp": "2026-03-09T08:47:00",
      "lat": 51.5154,
      "lon": -0.1755
    }
    // ...one entry per station
  ],
  "meta": {
    "total": 270,
    "count": 270,
    "page": 1,
    "per_page": 270,
    "total_pages": 1
  },
  "links": {
    "self": { "href": "/network/crowding", "method": "GET" }
  }
}
```

#### Field Reference — `CrowdingData`

| Field | Type | Description |
|-------|------|-------------|
| `station_id` | `string` | NaPTAN or TfL station identifier |
| `line_id` | `string \| null` | Line identifier if crowding is line-specific |
| `crowding_level` | `string \| null` | Categorical level: `low`, `medium`, `high`, `very_high` |
| `capacity_percentage` | `float \| null` | Fractional fill level (0.0 – 1.0+), where 1.0 = 100% full |
| `timestamp` | `string` | ISO 8601 datetime of when the reading was taken |
| `lat` | `float \| null` | Station latitude |
| `lon` | `float \| null` | Station longitude |

#### Example Prompt

> "Which stations are currently very crowded? Show me the top five by capacity percentage."

---

### `generate_network_report`

**File:** [src/adapters/reports_adapter.py](../src/adapters/reports_adapter.py)

Generates and persists a network status report based on the current state of disruptions, line statuses, and graph connectivity metrics. Optionally uses an LLM to produce a richer natural-language summary (controlled by the `USE_LLM_SUMMARIZER` environment variable).

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `request` | `CreateReportRequest` | Yes | — | JSON object with a `report_type` field |

**`CreateReportRequest` schema:**

| Field | Type | Allowed values | Default |
|-------|------|----------------|---------|
| `report_type` | `string` | `"snapshot"`, `"daily_summary"`, `"incident"` | `"snapshot"` |

- **`snapshot`** — Point-in-time capture of current network status.
- **`daily_summary`** — Aggregated summary intended for end-of-day review.
- **`incident`** — Focused report highlighting active disruptions and affected lines.

#### Response

Returns a `ResourceResponse<ReportData>` object.

```jsonc
{
  "data": {
    "id": 42,
    "timestamp": "2026-03-09T08:30:00",
    "report_type": "snapshot",
    "summary": "The network is operating normally with minor delays on the Central line...",
    "total_disruptions": 3,
    "active_lines_count": 11,
    "affected_lines_count": 1,
    "graph_connectivity_score": 0.94,
    "average_reliability_score": 0.91
  },
  "links": {
    "self": { "href": "/reports/42", "method": "POST" }
  }
}
```

#### Field Reference — `ReportData`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Auto-assigned database ID |
| `timestamp` | `string` | ISO 8601 generation time |
| `report_type` | `string` | One of `snapshot`, `daily_summary`, `incident` |
| `summary` | `string` | Human-readable summary text (template or LLM-generated) |
| `total_disruptions` | `integer` | Total active disruption records |
| `active_lines_count` | `integer` | Number of lines currently in service |
| `affected_lines_count` | `integer` | Number of lines with at least one active disruption |
| `graph_connectivity_score` | `float \| null` | 0–1 score representing how well-connected the network graph is |
| `average_reliability_score` | `float \| null` | 0–1 mean reliability derived from Bayesian disruption analysis |

#### Example Prompt

> "Generate a snapshot report of the current TfL network status."

---

## Response Envelope

All three tools return responses wrapped in a standard HATEOAS envelope (defined in [`src/data/api_models.py`](../src/data/api_models.py)):

### `ResourceResponse<T>` (single item)

```jsonc
{
  "data": { /* T */ },
  "links": {
    "self": { "href": "...", "method": "GET" }
    // additional relation links may be present
  }
}
```

### `CollectionResponse<T>` (list)

```jsonc
{
  "data": [ /* T[] */ ],
  "meta": {
    "total": 100,
    "count": 50,
    "page": 1,
    "per_page": 50,
    "total_pages": 2
  },
  "links": {
    "self": { "href": "...", "method": "GET" }
  }
}
```

---

## Environment Variables

The following variables affect MCP tool behaviour at runtime:

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_LLM_SUMMARIZER` | `false` | Set to `true` to use an LLM for `generate_network_report` summaries |
| `LLM_API_ENDPOINT` | — | LLM provider endpoint URL (required when `USE_LLM_SUMMARIZER=true`) |
| `LLM_API_KEY` | — | API key for the LLM provider |

---

## Architecture Notes

```
MCP Client (AI assistant)
        │  SSE connection to :9002
        ▼
  FastMCP Server  ─── mcp_provider.py
        │
        ├── plan_route          ──▶ journeys_adapter.py ──▶ RouteCalculationCommand ──▶ GraphManager
        ├── get_network_crowding ──▶ network_adapter.py  ──▶ CrowdingOperations     ──▶ DB
        └── generate_network_report ──▶ reports_adapter.py ──▶ NetworkReportingCommand ──▶ DB + Summarizer
```

The MCP server and the REST API share the same underlying command and data layers — the adapters are thin wrappers that translate tool arguments into command calls, then map the results back to the API model schema.
