import logging
from data.api_models import ResourceResponse
from data.hateoas import HateoasBuilder
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ApiRoot(BaseModel):
    title: str
    version: str
    description: str


async def root_handler():
    root_data = ApiRoot(
        title="TfL Nexus API",
        version="3.0.0",
        description="RESTful Transport for London Network Intelligence API"
    )

    additional_links = {
        "journeys": "/journeys",
        "lines": "/lines",
        "stations": "/stations",
        "disruptions": "/disruptions",
        "reports": "/reports",
        "network": "/network/topology",
        "data_imports": "/data-imports",
        "system_health": "/system/health",
        "system_statistics": "/system/statistics",
        "modes": "/modes",
        "disruption_categories": "/disruption-categories",
        "docs": "/docs"
    }

    links = HateoasBuilder.build_links("/", additional_links)

    return ResourceResponse(data=root_data, links=links)
