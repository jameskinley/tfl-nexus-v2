import networkx as nx
from io import BytesIO
import matplotlib.pyplot as plt

class GraphVisualiser:
    def __init__(self, graph : nx.Graph):
        self.graph = graph

    def draw(self):
        """
        Generate and return a visualization of the transport network graph.
        Returns a PNG image of the graph.
        """
        if self.graph.number_of_nodes() == 0:
            raise ValueError("No stations found in graph. Please run /route/ingest first.")
        
        plt.figure(figsize=(16, 12))
        pos = nx.spring_layout(self.graph, k=0.5, iterations=50)

        nx.draw_networkx_nodes(self.graph, pos, node_size=30, node_color='lightblue', alpha=0.8)
        nx.draw_networkx_edges(self.graph, pos, alpha=0.3, width=0.5)

        labels = {node: self.graph.nodes[node].get('name', node)[:15] for node in self.graph.nodes()}
        nx.draw_networkx_labels(self.graph, pos, labels, font_size=6)
                  
        plt.title(f"TfL Tube Network Graph\n{self.graph.number_of_nodes()} stations, {self.graph.number_of_edges()} connections", 
                fontsize=14, pad=20)
        plt.axis('off')
        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        return buf