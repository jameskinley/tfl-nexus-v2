from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from data.database import get_db
from commands.graph_operations import GraphOperationsCommand
import logging

router = APIRouter(prefix="/graph", tags=["Graph"])


@router.get(
    "/stats",
    summary="Get Graph Statistics",
    status_code=200,
    responses={
        200: {
            "description": "Successfully retrieved graph statistics",
            "content": {
                "application/json": {
                    "example": {
                        "nodes": 250,
                        "edges": 450,
                        "average_degree": 3.6,
                        "connected_components": 1,
                        "network_health": "good"
                    }
                }
            }
        },
        500: {
            "description": "Internal server error - graph building failed",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to build graph from database"}
                }
            }
        }
    }
)
async def get_graph_statistics(db: Session = Depends(get_db)):
    """
    Build the transport network graph from database and return statistics.
    
    Constructs an in-memory graph representation of the transport network and calculates
    various metrics including node count, edge count, average degree, and number of
    connected components.
    
    Args:
        db: Database session dependency.
    
    Returns:
        dict: Graph statistics including nodes, edges, average degree, and connected components.
    
    Raises:
        HTTPException: 500 if graph building fails.
    """
    try:
        command = GraphOperationsCommand(db)
        return command.get_graph_stats()
    except Exception as e:
        logging.error(f"Error building graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/visualize",
    summary="Visualize Transport Network Graph",
    status_code=200,
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Successfully generated graph visualization",
            "content": {
                "image/png": {
                    "example": "Binary PNG image data"
                }
            }
        },
        500: {
            "description": "Internal server error - visualization failed",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to generate visualization"}
                }
            }
        }
    }
)
async def visualize_graph(db: Session = Depends(get_db)):
    """
    Generate and return a visualization of the transport network graph as a PNG image.
    
    Creates a visual representation of the entire transport network graph showing
    stations as nodes and connections as edges. The visualization is returned as
    a PNG image stream.
    
    Args:
        db: Database session dependency.
    
    Returns:
        StreamingResponse: PNG image of the graph visualization.
    
    Raises:
        HTTPException: 500 if visualization generation fails.
    """
    try:
        command = GraphOperationsCommand(db)
        buf = command.visualize_graph()
        return StreamingResponse(buf, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error visualizing graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))
