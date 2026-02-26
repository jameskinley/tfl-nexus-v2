from mcp_provider import mcp
from data.database import SessionLocal
from data.api_models import CollectionResponse, CrowdingData, PaginationMeta
from commands.crowding_operations import CrowdingOperations
from data.hateoas import HateoasBuilder

@mcp.tool(
    name="get_network_crowding",
    title="Get Network Crowding Data",
    description="Retrieves current crowding levels across the network. Optional parameters should not be provided to this tool."
)
async def get_network_crowding() -> CollectionResponse[CrowdingData]:
    db = SessionLocal()
    try:
        crowding_ops = CrowdingOperations(db)
        heatmap_data = crowding_ops.get_crowding_heatmap()
        crowding_list = [
            CrowdingData(
                station_id=station_id,
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
    finally:
        db.close()
