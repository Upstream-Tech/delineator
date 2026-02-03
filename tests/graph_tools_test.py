"""
Tests for graph tools module.

These tests verify the correctness of graph operations used in river network analysis,
including stream order calculations (Strahler and Shreve), node operations, and
graph utilities.
"""

import networkx as nx
import pytest

from upstream_delineator.delineator_utils.graph_tools import (
    calculate_shreve_stream_order,
    calculate_strahler_stream_order,
    insert_node,
    make_river_network,
    prune_node,
    upstream_nodes,
)


class TestStreamOrderCalculations:
    """Test stream order calculation algorithms."""

    def create_simple_network(self) -> nx.DiGraph:
        """
        Create a simple test network with known structure.

        Structure (arrows show flow direction, toward right):
            A ─┐
               ├─> D ─> E
            B ─┘
            C ─────────┘

        Expected Strahler orders: A=1, B=1, C=1, D=2, E=2
        Expected Shreve orders: A=1, B=1, C=1, D=2, E=3
        """
        G = nx.DiGraph()
        G.add_edge("A", "D")
        G.add_edge("B", "D")
        G.add_edge("D", "E")
        G.add_edge("C", "E")
        return G

    def create_linear_network(self) -> nx.DiGraph:
        """
        Create a linear (unbranched) network.

        Structure: A ─> B ─> C ─> D

        All nodes should have Strahler order 1.
        Shreve orders: A=1, B=2, C=3, D=4
        """
        G = nx.DiGraph()
        G.add_edge("A", "B")
        G.add_edge("B", "C")
        G.add_edge("C", "D")
        return G

    def create_symmetric_network(self) -> nx.DiGraph:
        """
        Create a symmetric branching network where streams of equal order meet.

        Structure:
            A ─┐       ┌─ E
               ├─> C ─>│
            B ─┘       └─ F
            (plus D and G feeding into the junction at outlet H)

        When two streams of Strahler order n meet, the result is n+1.
        """
        G = nx.DiGraph()
        # Two headwaters feeding into C
        G.add_edge("A", "C")
        G.add_edge("B", "C")
        # Two more headwaters feeding into D
        G.add_edge("E", "D")
        G.add_edge("F", "D")
        # C and D meet at outlet
        G.add_edge("C", "outlet")
        G.add_edge("D", "outlet")
        return G

    def test_strahler_order_simple_network(self):
        """Test Strahler order calculation on simple branching network."""
        G = self.create_simple_network()
        G = calculate_strahler_stream_order(G)

        # Headwaters should have order 1
        assert G.nodes["A"]["strahler_order"] == 1
        assert G.nodes["B"]["strahler_order"] == 1
        assert G.nodes["C"]["strahler_order"] == 1

        # D receives two streams of order 1, so it becomes order 2
        assert G.nodes["D"]["strahler_order"] == 2

        # E receives order 2 from D and order 1 from C, so max is 2
        assert G.nodes["E"]["strahler_order"] == 2

    def test_strahler_order_linear_network(self):
        """Test Strahler order on linear (unbranched) network."""
        G = self.create_linear_network()
        G = calculate_strahler_stream_order(G)

        # All nodes in unbranched network should have order 1
        for node in G.nodes():
            assert G.nodes[node]["strahler_order"] == 1, (
                f"Node {node} should have Strahler order 1"
            )

    def test_strahler_order_symmetric_network(self):
        """Test Strahler order on symmetric branching network."""
        G = self.create_symmetric_network()
        G = calculate_strahler_stream_order(G)

        # Headwaters should have order 1
        for node in ["A", "B", "E", "F"]:
            assert G.nodes[node]["strahler_order"] == 1, (
                f"Headwater {node} should have order 1"
            )

        # C and D both receive two order-1 streams, so they become order 2
        assert G.nodes["C"]["strahler_order"] == 2
        assert G.nodes["D"]["strahler_order"] == 2

        # Outlet receives two order-2 streams, so it becomes order 3
        assert G.nodes["outlet"]["strahler_order"] == 3

    def test_shreve_order_simple_network(self):
        """Test Shreve order calculation on simple branching network."""
        G = self.create_simple_network()
        G = calculate_shreve_stream_order(G)

        # Headwaters should have order 1
        assert G.nodes["A"]["shreve_order"] == 1
        assert G.nodes["B"]["shreve_order"] == 1
        assert G.nodes["C"]["shreve_order"] == 1

        # D receives inputs from A and B
        assert G.nodes["D"]["shreve_order"] == 2

        # E receives inputs from D and C (Shreve order is max + 1)
        assert G.nodes["E"]["shreve_order"] == 3

    def test_shreve_order_linear_network(self):
        """Test Shreve order on linear network - should increase downstream."""
        G = self.create_linear_network()
        G = calculate_shreve_stream_order(G)

        # Shreve order increases by 1 at each step
        assert G.nodes["A"]["shreve_order"] == 1
        assert G.nodes["B"]["shreve_order"] == 2
        assert G.nodes["C"]["shreve_order"] == 3
        assert G.nodes["D"]["shreve_order"] == 4

    def test_shreve_order_symmetric_network(self):
        """Test Shreve order on symmetric branching network."""
        G = self.create_symmetric_network()
        G = calculate_shreve_stream_order(G)

        # Headwaters should have order 1
        for node in ["A", "B", "E", "F"]:
            assert G.nodes[node]["shreve_order"] == 1

        # C and D both receive two streams
        assert G.nodes["C"]["shreve_order"] == 2
        assert G.nodes["D"]["shreve_order"] == 2

        # Outlet receives from both C and D
        assert G.nodes["outlet"]["shreve_order"] == 3


class TestNodeOperations:
    """Test node insertion and pruning operations."""

    def test_prune_node_middle(self):
        """Test pruning a node from the middle of a network."""
        G = nx.DiGraph()
        G.add_edge("A", "B")
        G.add_edge("B", "C")

        G = prune_node(G, "B")

        # B should be gone
        assert "B" not in G.nodes()

        # A should now connect directly to C
        assert G.has_edge("A", "C")

    def test_prune_node_branch(self):
        """Test pruning a node that has multiple predecessors."""
        G = nx.DiGraph()
        G.add_edge("A", "X")
        G.add_edge("B", "X")
        G.add_edge("X", "C")

        G = prune_node(G, "X")

        # X should be gone
        assert "X" not in G.nodes()

        # Both A and B should now connect to C
        assert G.has_edge("A", "C")
        assert G.has_edge("B", "C")

    def test_prune_node_preserves_other_edges(self):
        """Test that pruning preserves edges not involving the pruned node."""
        G = nx.DiGraph()
        G.add_edge("A", "B")
        G.add_edge("B", "C")
        G.add_edge("D", "C")

        G = prune_node(G, "B")

        # D -> C edge should still exist
        assert G.has_edge("D", "C")

    def test_prune_nonexistent_node_raises(self):
        """Test that pruning a non-existent node raises ValueError."""
        G = nx.DiGraph()
        G.add_node("A")

        with pytest.raises(ValueError, match="not in the graph"):
            prune_node(G, "nonexistent")

    def test_insert_node_into_leaf(self):
        """Test inserting a node into a leaf (Strahler order 1) catchment."""
        G = nx.DiGraph()
        G.add_edge("A", "B")
        G.add_edge("B", "C")
        # Add strahler_order attribute for A (leaf node)
        G.nodes["A"]["strahler_order"] = 1
        G.nodes["B"]["strahler_order"] = 1
        G.nodes["C"]["strahler_order"] = 1

        G = insert_node(G, "new_node", "A")

        # New node should exist
        assert "new_node" in G.nodes()

        # New node should connect to A
        assert G.has_edge("new_node", "A")

        # New node should be marked as 'new' and 'leaf' type
        assert G.nodes["new_node"]["new"] is True
        assert G.nodes["new_node"]["type"] == "leaf"

    def test_insert_node_into_stem(self):
        """Test inserting a node into a stem (Strahler order > 1) catchment."""
        G = nx.DiGraph()
        G.add_edge("A", "B")
        G.add_edge("C", "B")
        G.add_edge("B", "D")
        # B is at a junction, so it has order > 1
        G.nodes["A"]["strahler_order"] = 1
        G.nodes["C"]["strahler_order"] = 1
        G.nodes["B"]["strahler_order"] = 2
        G.nodes["D"]["strahler_order"] = 2

        G = insert_node(G, "new_node", "B")

        # New node should exist
        assert "new_node" in G.nodes()

        # New node should connect to B
        assert G.has_edge("new_node", "B")

        # A and C should now connect to new_node instead of B
        assert G.has_edge("A", "new_node")
        assert G.has_edge("C", "new_node")
        assert not G.has_edge("A", "B")
        assert not G.has_edge("C", "B")

        # New node should be marked as 'new' and 'stem' type
        assert G.nodes["new_node"]["new"] is True
        assert G.nodes["new_node"]["type"] == "stem"


class TestUpstreamNodes:
    """Test the upstream_nodes function."""

    def test_upstream_nodes_simple(self):
        """Test finding upstream nodes in a simple network."""
        G = nx.DiGraph()
        G.add_edge("A", "B")
        G.add_edge("B", "C")

        # From C's perspective
        up = upstream_nodes(G, "C")
        assert set(up) == {"A", "B"}

        # From B's perspective
        up = upstream_nodes(G, "B")
        assert set(up) == {"A"}

        # From A's perspective (headwater, no upstream)
        up = upstream_nodes(G, "A")
        assert len(up) == 0

    def test_upstream_nodes_branching(self):
        """Test finding upstream nodes in a branching network."""
        G = nx.DiGraph()
        G.add_edge("A", "C")
        G.add_edge("B", "C")
        G.add_edge("C", "D")

        # From D's perspective
        up = upstream_nodes(G, "D")
        assert set(up) == {"A", "B", "C"}

        # From C's perspective
        up = upstream_nodes(G, "C")
        assert set(up) == {"A", "B"}

    def test_upstream_nodes_nonexistent_raises(self):
        """Test that requesting upstream of non-existent node raises error."""
        G = nx.DiGraph()
        G.add_node("A")

        with pytest.raises(ValueError, match="not in the graph"):
            upstream_nodes(G, "nonexistent")


class TestMakeRiverNetwork:
    """Test the make_river_network function."""

    def test_make_river_network_from_dataframe(self):
        """Test creating a network graph from a DataFrame."""
        import pandas as pd

        # Create a simple DataFrame mimicking subbasin data
        data = {
            "nextdown": [2, 3, 0],  # Node 1 -> 2, 2 -> 3, 3 -> outlet (0)
            "unitarea": [100.0, 150.0, 200.0],
        }
        df = pd.DataFrame(data, index=[1, 2, 3])

        G = make_river_network(df, terminal_node=3)

        # Should have 3 nodes
        assert G.number_of_nodes() == 3

        # Check edges (terminal node 3 should not have outgoing edge)
        assert G.has_edge(1, 2)
        assert G.has_edge(2, 3)
        assert not G.has_edge(3, 0)  # No edge to 0 for terminal

        # Check area attributes
        assert G.nodes[1]["area"] == 100.0
        assert G.nodes[2]["area"] == 150.0
        assert G.nodes[3]["area"] == 200.0

    def test_make_river_network_handles_zero_nextdown(self):
        """Test that nextdown=0 (ocean/terminal) is handled correctly."""
        import pandas as pd

        data = {
            "nextdown": [0],  # Single terminal node
            "unitarea": [100.0],
        }
        df = pd.DataFrame(data, index=[1])

        G = make_river_network(df)

        # Should have 1 node, no edges
        assert G.number_of_nodes() == 1
        assert G.number_of_edges() == 0
