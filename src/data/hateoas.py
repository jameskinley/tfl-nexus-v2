from typing import Dict, Optional
from data.api_models import Link, Links
from urllib.parse import quote

class HateoasBuilder:
    
    @staticmethod
    def build_links(self_href: str, additional_links: Optional[Dict[str, str]] = None, method: str = "GET") -> Links:
        links_dict = {"self": Link(href=self_href, method=method)}
        
        if additional_links:
            for rel, href in additional_links.items():
                links_dict[rel] = Link(href=href, rel=rel)
        
        return Links(**links_dict)
    
    @staticmethod
    def encode_station_identifier(identifier: str) -> str:
        return quote(identifier, safe='')
    
    @staticmethod
    def build_pagination_links(base_path: str, page: int, per_page: int, total_pages: int, query_params: Optional[Dict[str, str]] = None) -> Links:
        def build_url(page_num: int) -> str:
            url = f"{base_path}?page={page_num}&per_page={per_page}"
            if query_params:
                for key, value in query_params.items():
                    if key not in ['page', 'per_page']:
                        url += f"&{key}={quote(str(value), safe='')}"
            return url
        
        links_dict = {
            "self": Link(href=build_url(page)),
            "first": Link(href=build_url(1)),
            "last": Link(href=build_url(total_pages))
        }
        
        if page > 1:
            links_dict["prev"] = Link(href=build_url(page - 1), rel="prev")
        
        if page < total_pages:
            links_dict["next"] = Link(href=build_url(page + 1), rel="next")
        
        return Links(**links_dict)
    
    @staticmethod
    def station_links(station_id: str) -> Dict[str, str]:
        encoded_id = HateoasBuilder.encode_station_identifier(station_id)
        return {
            "lines": f"/stations/{encoded_id}/lines",
            "crowding": f"/stations/{encoded_id}/crowding",
            "connections": f"/stations/{encoded_id}/connections",
            "disruptions": f"/stations/{encoded_id}/disruptions"
        }
    
    @staticmethod
    def line_links(line_id: str) -> Dict[str, str]:
        return {
            "routes": f"/lines/{line_id}/routes",
            "stations": f"/lines/{line_id}/stations",
            "disruptions": f"/lines/{line_id}/disruptions",
            "schedules": f"/lines/{line_id}/schedules"
        }
    
    @staticmethod
    def disruption_links(disruption_id: str) -> Dict[str, str]:
        return {
            "events": f"/disruptions/{disruption_id}/events",
            "affected_stations": f"/disruptions/{disruption_id}/affected-stations"
        }
    
    @staticmethod
    def journey_links(origin: str, destination: str) -> Dict[str, str]:
        origin_encoded = HateoasBuilder.encode_station_identifier(origin)
        dest_encoded = HateoasBuilder.encode_station_identifier(destination)
        return {
            "origin": f"/stations/{origin_encoded}",
            "destination": f"/stations/{dest_encoded}"
        }
