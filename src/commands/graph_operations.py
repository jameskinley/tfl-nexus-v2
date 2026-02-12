from sqlalchemy.orm import Session
from graph.graph_manager import GraphManager
from graph.graph_visualiser import GraphVisualiser
from io import BytesIO


class GraphOperationsCommand:
    def __init__(self, db_session: Session):
        self.db_session = db_session

    def get_graph_stats(self) -> dict:
        graph_manager = GraphManager()
        graph = graph_manager.build_graph_from_db_with_disruptions(self.db_session)
        
        avg_degree = 0.0
        if graph.number_of_nodes() > 0:
            avg_degree = (2 * graph.number_of_edges()) / graph.number_of_nodes()
        
        return {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "average_degree": round(avg_degree, 2),
            "connected_components": len(list(graph.connected_components())) if hasattr(graph, 'connected_components') else 1
        }

    def visualize_graph(self) -> BytesIO:
        graph_manager = GraphManager()
        graph = graph_manager.build_graph_from_db_with_disruptions(self.db_session)
        visualiser = GraphVisualiser(graph)
        buf = visualiser.draw()
        return buf
