"""
Example usage of GraphManager with the SQLAlchemy database.

Run this after ingesting data to build and test the graph.
"""
from ..data.database import get_db_session
from .graph_manager import GraphManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_and_analyze_graph():
    """Build graph from database and print statistics"""
    
    with get_db_session() as session:
        # Initialize graph manager
        graph_manager = GraphManager()
        
        # Build graph from database
        graph = graph_manager.build_graph_from_db(session)
        
        # Print statistics
        logger.info(f"Graph Statistics:")
        logger.info(f"  Nodes (stations): {graph.number_of_nodes()}")
        logger.info(f"  Edges (connections): {graph.number_of_edges()}")
        
        # Calculate average degree (2 * edges / nodes for undirected graph)
        if graph.number_of_nodes() > 0:
            avg_degree = (2 * graph.number_of_edges()) / graph.number_of_nodes()
            logger.info(f"  Average degree: {avg_degree:.2f}")
        
        # Show sample nodes
        sample_nodes = list(graph.nodes(data=True))[:3]
        logger.info(f"\nSample stations:")
        for node_id, node_data in sample_nodes:
            logger.info(f"  {node_data['name']} (ID: {node_id})")
            logger.info(f"    Lines: {', '.join(node_data['lines'])}")
            logger.info(f"    Modes: {', '.join(node_data['modes'])}")
        
        # Show sample edges
        sample_edges = list(graph.edges(data=True))[:3]
        logger.info(f"\nSample connections:")
        for source, target, edge_data in sample_edges:
            source_name = graph.nodes[source]['name']
            target_name = graph.nodes[target]['name']
            logger.info(f"  {source_name} → {target_name}")
            logger.info(f"    Time: {edge_data['time_distance']:.2f} min")
            logger.info(f"    Line: {edge_data['line']}")
            logger.info(f"    Mode: {edge_data['mode']}")
        
        return graph_manager


def find_route_example(from_station: str, to_station: str):
    """
    Example of finding a route between two stations.
    
    Args:
        from_station: Station name (e.g., "King's Cross St. Pancras")
        to_station: Station name (e.g., "Heathrow Terminal 5")
    """
    from datetime import time
    
    with get_db_session() as session:
        graph_manager = GraphManager()
        graph_manager.build_graph_from_db(session)
        
        # Find station IDs by name
        from_id = None
        to_id = None
        
        for node_id, node_data in graph_manager.graph.nodes(data=True):
            if from_station.lower() in node_data['name'].lower():
                from_id = node_id
                logger.info(f"Found origin: {node_data['name']}")
            if to_station.lower() in node_data['name'].lower():
                to_id = node_id
                logger.info(f"Found destination: {node_data['name']}")
        
        if not from_id or not to_id:
            logger.error("Could not find one or both stations")
            return
        
        # Example 1: Find route at off-peak time (2:00 PM)
        try:
            logger.info(f"\n=== Route at 2:00 PM (Off-Peak) ===")
            path_offpeak = graph_manager.route_time_only(from_id, to_id, current_time="14:00")
            print_route_details(graph_manager, path_offpeak, "Off-Peak (14:00)")
        except Exception as e:
            logger.error(f"Error finding off-peak route: {e}")
        
        # Example 2: Find route at peak time (8:30 AM)
        try:
            logger.info(f"\n=== Route at 8:30 AM (Peak) ===")
            path_peak = graph_manager.route_time_only(from_id, to_id, current_time=time(8, 30))
            print_route_details(graph_manager, path_peak, "Peak (08:30)")
        except Exception as e:
            logger.error(f"Error finding peak route: {e}")
        
        # Example 3: Find route with no time (uses base times)
        try:
            logger.info(f"\n=== Route with Static Times ===")
            path_static = graph_manager.route_time_only(from_id, to_id)
            print_route_details(graph_manager, path_static, "Static")
        except Exception as e:
            logger.error(f"Error finding static route: {e}")


def print_route_details(graph_manager, path, label):
    """Helper to print route details"""
    logger.info(f"\n{label} Route:")
    total_time = 0
    
    for i in range(len(path)):
        station_name = graph_manager.graph.nodes[path[i]]['name']
        
        if i < len(path) - 1:
            next_station = path[i + 1]
            edge_data = graph_manager.graph[path[i]][next_station]
            time_cost = edge_data.get('time_distance', edge_data.get('base_time', 0))
            total_time += time_cost
            
            logger.info(f"  {i+1}. {station_name}")
            logger.info(f"     ↓ {time_cost:.1f} min via {edge_data['line']} ({edge_data['mode']})")
        else:
            logger.info(f"  {i+1}. {station_name}")
    
    logger.info(f"\nTotal journey time: {total_time:.1f} minutes")
    logger.info(f"Stations: {len(path)}")



if __name__ == "__main__":
    # Build and analyze graph
    build_and_analyze_graph()
    
    # Example route finding (uncomment and modify stations as needed)
    # find_route_example("King's Cross", "Heathrow")
