from fastapi import APIRouter, HTTPException, Path
from commands.meta_operations import MetaOperationsCommand
from data.api_models import ResourceResponse, CollectionResponse, ModeData, PaginationMeta
from data.hateoas import HateoasBuilder
from pydantic import BaseModel
from typing import List
import logging

router = APIRouter(tags=["Reference Data"])
logger = logging.getLogger(__name__)


class DisruptionCategoriesData(BaseModel):
    categories: List[str]


@router.get(
    "/disruption-categories",
    response_model=ResourceResponse[DisruptionCategoriesData],
    summary="List Disruption Categories",
    status_code=200
)
async def list_disruption_categories() -> ResourceResponse[DisruptionCategoriesData]:
    try:
        command = MetaOperationsCommand()
        categories = command.get_disruption_categories()
        
        data = DisruptionCategoriesData(categories=categories)
        
        links = HateoasBuilder.build_links("/disruption-categories")
        
        return ResourceResponse(data=data, links=links)
    
    except Exception as e:
        logger.error(f"Error fetching disruption categories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/modes",
    response_model=CollectionResponse[ModeData],
    summary="List Transport Modes",
    status_code=200
)
async def list_modes() -> CollectionResponse[ModeData]:
    try:
        command = MetaOperationsCommand()
        modes_raw = command.get_modes()
        
        modes = [
            ModeData(
                id=mode['id'],
                name=mode['name'],
                is_tfl_service=mode['is_tfl_service'],
                is_scheduled_service=mode['is_scheduled_service']
            )
            for mode in modes_raw
        ]
        
        meta = PaginationMeta(
            total=len(modes),
            count=len(modes),
            page=1,
            per_page=len(modes),
            total_pages=1
        )
        
        links = HateoasBuilder.build_links("/modes")
        
        return CollectionResponse(data=modes, meta=meta, links=links)
    
    except Exception as e:
        logger.error(f"Error fetching modes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/modes/{mode_id}",
    response_model=ResourceResponse[ModeData],
    summary="Get Transport Mode Details",
    status_code=200
)
async def get_mode(
    mode_id: str = Path(..., description="Mode ID")
) -> ResourceResponse[ModeData]:
    try:
        command = MetaOperationsCommand()
        modes_raw = command.get_modes()
        
        mode_raw = next((m for m in modes_raw if m['id'] == mode_id), None)
        
        if not mode_raw:
            raise HTTPException(status_code=404, detail=f"Mode '{mode_id}' not found")
        
        mode_data = ModeData(
            id=mode_raw['id'],
            name=mode_raw['name'],
            is_tfl_service=mode_raw['is_tfl_service'],
            is_scheduled_service=mode_raw['is_scheduled_service']
        )
        
        self_href = f"/modes/{mode_id}"
        additional_links = {
            "lines": f"/lines?mode={mode_id}"
        }
        links = HateoasBuilder.build_links(self_href, additional_links)
        
        return ResourceResponse(data=mode_data, links=links)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
