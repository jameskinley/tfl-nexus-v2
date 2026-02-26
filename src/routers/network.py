from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any
from data.database import get_db
from commands.graph_operations import GraphOperationsCommand
from commands.crowding_operations import CrowdingOperations
from data.api_models import ResourceResponse, NetworkTopologyData, CrowdingData, CollectionResponse, PaginationMeta
from data.hateoas import HateoasBuilder
import logging
router = APIRouter(prefix="/network", tags=["Network"])
logger = logging.getLogger(__name__)

@router.get(
    "/topology",
    response_model=ResourceResponse[NetworkTopologyData],
    summary="Get Network Topology Metrics",
    status_code=200
)
async def get_network_topology(
    db: Session = Depends(get_db)
) -> ResourceResponse[NetworkTopologyData]:
    try:
        command = GraphOperationsCommand(db)
        stats = command.get_graph_stats()
        
        topology_data = NetworkTopologyData(
            nodes=stats['nodes'],
            edges=stats['edges'],
            average_degree=stats['average_degree'],
            connected_components=stats['connected_components'],
            network_health=stats.get('network_health', 'unknown')
        )
        
        self_href = "/network/topology"
        additional_links = {
            "visualization": "/network/topology/visualization"
        }
        links = HateoasBuilder.build_links(self_href, additional_links)
        
        return ResourceResponse(data=topology_data, links=links)
    
    except Exception as e:
        logger.error(f"Error fetching network topology: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/topology/visualization",
    summary="Get Network Topology Visualization",
    status_code=200,
    response_class=StreamingResponse
)
async def get_network_visualization(
    db: Session = Depends(get_db)
) -> StreamingResponse:
    try:
        command = GraphOperationsCommand(db)
        buf = command.visualize_graph()
        return StreamingResponse(buf, media_type="image/png")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating network visualization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/crowding",
    response_model=CollectionResponse[CrowdingData],
    summary="Get Network-Wide Crowding Data",
    status_code=200
)
async def get_network_crowding(
    db: Any = Depends(get_db)
) -> CollectionResponse[CrowdingData]:
    try:
        crowding_ops = CrowdingOperations(db)
        heatmap_data = crowding_ops.get_crowding_heatmap()
        
        crowding_list = [
            CrowdingData(
                station_id=station_id, #type: ignore
                line_id=None,
                crowding_level=None,
                capacity_percentage=data['crowding_level'],
                timestamp=data['timestamp'],
                lat=data['lat'],
                lon=data['lon']
            )
            for station_id, data in heatmap_data.items()
        ]
        
        meta = PaginationMeta(
            total=len(crowding_list),
            count=len(crowding_list),
            page=1,
            per_page=len(crowding_list),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links("/network/crowding")
        
        return CollectionResponse(data=crowding_list, meta=meta, links=links)
    
    except Exception as e:
        logger.error(f"Error fetching network crowding: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
