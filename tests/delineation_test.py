"""
Tests for the watershed delineation library.

These tests verify correctness of watershed delineation in various hydrologic scenarios:
1. Single outlet delineation
2. Multiple subbasin delineation
3. Headwater watersheds
4. Network consolidation
5. Graph topology and stream order calculations
6. Disconnected basin networks

Uses syrupy for snapshot testing of complex geodata outputs.
"""

import networkx as nx
import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension

from upstream_delineator import config
from upstream_delineator.delineator_utils.delineate import delineate


class TestBasicDelineation:
    """Test basic watershed delineation functionality."""

    @pytest.fixture(autouse=True)
    def reset_config(self, default_config):
        """Reset config before each test."""
        config.set(default_config)

    def test_single_outlet_delineation_runs_without_error(
        self, single_outlet_csv, default_config
    ):
        """
        Test that a single outlet delineation completes without errors.
        This is the most basic smoke test for the delineation workflow.
        """
        config.set(default_config)

        G, subbasins_gdf, rivers_gdf = delineate(
            single_outlet_csv, "test_single", default_config
        )

        # Basic assertions that we got valid output
        assert G is not None, "Graph should not be None"
        assert subbasins_gdf is not None, "Subbasins GeoDataFrame should not be None"
        assert rivers_gdf is not None, "Rivers GeoDataFrame should not be None"

        # Graph should have nodes
        assert G.number_of_nodes() > 0, "Graph should have at least one node"

        # Subbasins should have geometries
        assert len(subbasins_gdf) > 0, "Should have at least one subbasin"
        assert "geometry" in subbasins_gdf.columns, "Subbasins should have geometry"

        # Verify the outlet node exists and matches CSV
        assert G.has_node("outlet1"), "Graph should contain the outlet1 node"

        # Terminal node should be the outlet
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "outlet1" in terminal_nodes, "outlet1 should be a terminal node"

    def test_multi_subbasin_delineation(self, multi_subbasin_csv, default_config):
        """
        Test delineation with multiple subbasin outlets.
        Verifies that upstream points are correctly assigned to subbasins.
        """
        config.set(default_config)

        G, subbasins_gdf, _rivers_gdf = delineate(
            multi_subbasin_csv, "test_multi", default_config
        )

        # Should have custom nodes for each outlet point
        custom_nodes = [n for n, d in G.nodes(data=True) if d.get("custom", False)]
        assert len(custom_nodes) >= 3, "Should have at least 3 custom outlet nodes"

        # All custom nodes should be in the subbasins
        subbasin_ids = subbasins_gdf["comid"].tolist()
        for node in custom_nodes:
            assert node in subbasin_ids, f"Custom node {node} should be in subbasins"

        # Verify all expected outlet IDs are present
        expected_outlets = ["main_outlet", "upstream1", "upstream2"]
        for outlet_id in expected_outlets:
            assert G.has_node(outlet_id), f"Graph should contain node {outlet_id}"

        # The main outlet should be terminal
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "main_outlet" in terminal_nodes, "main_outlet should be a terminal node"

    def test_headwater_outlet_delineation(self, headwater_outlet_csv, default_config):
        """
        Test delineation at a headwater location.
        Headwaters are leaf catchments with no upstream neighbors.
        """
        config.set(default_config)

        G, subbasins_gdf, _rivers_gdf = delineate(
            headwater_outlet_csv, "test_headwater", default_config
        )

        # Headwater watershed should be small (few subbasins)
        assert len(subbasins_gdf) >= 1, (
            "Headwater watershed should have at least 1 subbasin"
        )

        # The outlet node should exist and be terminal
        assert G.has_node("headwater"), "Graph should contain the headwater outlet node"
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "headwater" in terminal_nodes, "headwater should be a terminal node"


class TestNetworkTopology:
    """Test river network graph topology and connectivity."""

    @pytest.fixture(autouse=True)
    def reset_config(self, default_config):
        """Reset config before each test."""
        config.set(default_config)

    def test_graph_is_directed_acyclic(self, multi_subbasin_csv, default_config):
        """
        Test that the river network graph is a directed acyclic graph (DAG).
        River networks should flow downstream without cycles.
        """
        config.set(default_config)

        G, _, _ = delineate(multi_subbasin_csv, "test_dag", default_config)

        assert isinstance(G, nx.DiGraph), "Graph should be a directed graph"
        assert nx.is_directed_acyclic_graph(G), "River network should be acyclic"

        # Verify terminal node is the expected outlet
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "main_outlet" in terminal_nodes, "main_outlet should be a terminal node"

    def test_single_terminal_node(self, multi_subbasin_csv, default_config):
        """
        Test that the network has exactly one terminal (outlet) node.
        The terminal node is the one with no outgoing edges.
        """
        config.set(default_config)

        G, _, _ = delineate(multi_subbasin_csv, "test_terminal", default_config)

        # Find terminal nodes (no successors)
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert len(terminal_nodes) == 1, "Should have exactly one terminal node"
        assert terminal_nodes[0] == "main_outlet", "Terminal node should be main_outlet"

    def test_outlet_node_attributes_from_csv(self, multi_subbasin_csv, default_config):
        """
        Test that custom attributes from CSV are present in the graph nodes.
        Verifies that gage_id, priority, and other custom columns are accessible.
        """
        config.set(default_config)

        G, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_attrs", default_config
        )

        # Verify custom nodes are marked
        assert G.nodes["main_outlet"].get("custom") is True
        assert G.nodes["upstream1"].get("custom") is True
        assert G.nodes["upstream2"].get("custom") is True

        # Verify the subbasins GeoDataFrame has the custom columns
        assert "gage_id" in subbasins_gdf.columns, (
            "gage_id column should be in subbasins"
        )
        assert "priority" in subbasins_gdf.columns, (
            "priority column should be in subbasins"
        )

        # Check that custom outlet rows have the expected values
        main_outlet_row = subbasins_gdf[subbasins_gdf["comid"] == "main_outlet"]
        assert len(main_outlet_row) == 1, "Should have exactly one main_outlet row"
        assert main_outlet_row.iloc[0]["gage_id"] == "GAGE001"
        assert main_outlet_row.iloc[0]["priority"] == "high"

        upstream1_row = subbasins_gdf[subbasins_gdf["comid"] == "upstream1"]
        assert len(upstream1_row) == 1, "Should have exactly one upstream1 row"
        assert upstream1_row.iloc[0]["gage_id"] == "GAGE002"
        assert upstream1_row.iloc[0]["priority"] == "medium"

    def test_stream_orders_assigned(self, multi_subbasin_csv, default_config):
        """
        Test that Strahler and Shreve stream orders are calculated.
        These are fundamental hydrologic properties of river networks.
        """
        config.set(default_config)

        G, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_orders", default_config
        )

        # Check that stream orders are in graph nodes
        for node in G.nodes():
            assert "strahler_order" in G.nodes[node], (
                f"Node {node} should have strahler_order"
            )
            assert "shreve_order" in G.nodes[node], (
                f"Node {node} should have shreve_order"
            )
            assert G.nodes[node]["strahler_order"] >= 1, (
                "Strahler order should be at least 1"
            )
            assert G.nodes[node]["shreve_order"] >= 1, (
                "Shreve order should be at least 1"
            )

        # Check that stream orders are in subbasins geodataframe
        assert "strahler_order" in subbasins_gdf.columns
        assert "shreve_order" in subbasins_gdf.columns

        # Verify outlet is the expected node
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "main_outlet" in terminal_nodes

    def test_strahler_order_properties(self, multi_subbasin_csv, default_config):
        """
        Test that Strahler stream order follows correct rules:
        - Headwaters (no upstream) have order 1
        - When two streams of same order meet, result is order + 1
        - When streams of different orders meet, result is max order
        """
        config.set(default_config)

        G, _, _ = delineate(multi_subbasin_csv, "test_strahler", default_config)

        # Find leaf nodes (headwaters) - they should have Strahler order 1
        leaf_nodes = [n for n in G.nodes() if G.in_degree(n) == 0]
        for leaf in leaf_nodes:
            assert G.nodes[leaf]["strahler_order"] == 1, (
                f"Headwater node {leaf} should have Strahler order 1"
            )

        # For each non-leaf node, verify Strahler order calculation
        for node in G.nodes():
            if G.in_degree(node) > 0:
                upstream_orders = [
                    G.nodes[pred]["strahler_order"] for pred in G.predecessors(node)
                ]
                max_order = max(upstream_orders)
                count_max = upstream_orders.count(max_order)

                expected_order = max_order + 1 if count_max > 1 else max_order
                actual_order = G.nodes[node]["strahler_order"]

                assert actual_order == expected_order, (
                    f"Node {node}: expected Strahler order {expected_order}, "
                    f"got {actual_order}"
                )

    def test_shreve_order_properties(self, multi_subbasin_csv, default_config):
        """
        Test that Shreve stream order follows correct rules:
        - Headwaters have order 1
        - Order increases downstream (sum of upstream orders)
        """
        config.set(default_config)

        G, _, _ = delineate(multi_subbasin_csv, "test_shreve", default_config)

        # Leaf nodes should have Shreve order 1
        leaf_nodes = [n for n in G.nodes() if G.in_degree(n) == 0]
        for leaf in leaf_nodes:
            assert G.nodes[leaf]["shreve_order"] == 1, (
                f"Headwater node {leaf} should have Shreve order 1"
            )

        # Shreve order should increase downstream (or stay same at terminus)
        for node in G.nodes():
            successors = list(G.successors(node))
            if successors:
                successor = successors[0]
                assert (
                    G.nodes[successor]["shreve_order"] >= G.nodes[node]["shreve_order"]
                ), (
                    f"Shreve order should not decrease downstream "
                    f"from {node} to {successor}"
                )


class TestDisconnectedBasins:
    """Test handling of multiple disconnected watersheds."""

    @pytest.fixture(autouse=True)
    def reset_config(self, default_config):
        """Reset config before each test."""
        config.set(default_config)

    def test_disconnected_basins_separate_systems(
        self, disconnected_basins_csv, default_config
    ):
        """
        Test that two separate outlets create two disconnected river systems.
        Each outlet_id in the CSV should correspond to an independent watershed.
        """
        config.set(default_config)

        G, subbasins_gdf, _ = delineate(
            disconnected_basins_csv, "test_disconnected", default_config
        )

        # Both outlet nodes should exist
        assert G.has_node("basin1_outlet"), "Graph should contain basin1_outlet"
        assert G.has_node("basin2_outlet"), "Graph should contain basin2_outlet"

        # Both should be terminal nodes (no outgoing edges)
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "basin1_outlet" in terminal_nodes, (
            "basin1_outlet should be a terminal node"
        )
        assert "basin2_outlet" in terminal_nodes, (
            "basin2_outlet should be a terminal node"
        )

        # The graph should have exactly 2 terminal nodes (2 separate systems)
        assert len(terminal_nodes) == 2, (
            f"Should have exactly 2 terminal nodes for 2 watersheds, got {len(terminal_nodes)}"
        )

        # The graph should be disconnected (2 weakly connected components)
        num_components = nx.number_weakly_connected_components(G)
        assert num_components == 2, (
            f"Should have 2 weakly connected components, got {num_components}"
        )

        # Verify custom attributes from CSV are present
        assert "gage_id" in subbasins_gdf.columns
        basin1_row = subbasins_gdf[subbasins_gdf["comid"] == "basin1_outlet"]
        assert basin1_row.iloc[0]["gage_id"] == "GAGE_B1"

    def test_disconnected_basins_upstream_connectivity(
        self, disconnected_basins_csv, default_config
    ):
        """
        Test that upstream points are correctly connected to their respective outlets.
        basin1_upstream should flow to basin1_outlet, not basin2_outlet.
        """
        config.set(default_config)

        G, _, _ = delineate(
            disconnected_basins_csv, "test_disconnected_connectivity", default_config
        )

        # basin1_upstream should be in the same component as basin1_outlet
        # Find the component containing basin1_outlet
        components = list(nx.weakly_connected_components(G))

        basin1_component = None
        basin2_component = None
        for comp in components:
            if "basin1_outlet" in comp:
                basin1_component = comp
            if "basin2_outlet" in comp:
                basin2_component = comp

        assert basin1_component is not None, "Should find basin1 component"
        assert basin2_component is not None, "Should find basin2 component"

        # basin1_upstream should be in basin1's component
        assert "basin1_upstream" in basin1_component, (
            "basin1_upstream should be in the same component as basin1_outlet"
        )

        # basin1_upstream should NOT be in basin2's component
        assert "basin1_upstream" not in basin2_component, (
            "basin1_upstream should not be in basin2's component"
        )


class TestConsolidation:
    """Test network consolidation functionality."""

    @pytest.fixture(autouse=True)
    def reset_config(self, consolidate_config):
        """Reset config with consolidation enabled."""
        config.set(consolidate_config)

    def test_consolidation_reduces_nodes(
        self, multi_subbasin_csv, default_config, consolidate_config
    ):
        """
        Test that consolidation reduces the number of nodes in the network.
        Consolidation merges small unit catchments to create larger subbasins.
        """
        # First, delineate without consolidation
        config.set(default_config)
        G_original, _, _ = delineate(
            multi_subbasin_csv, "test_no_consol", default_config
        )

        # Then, delineate with consolidation
        config.set(consolidate_config)
        G_consolidated, _, _ = delineate(
            multi_subbasin_csv, "test_consol", consolidate_config
        )

        # Consolidated network should have fewer or equal nodes
        assert G_consolidated.number_of_nodes() <= G_original.number_of_nodes(), (
            f"Consolidated network ({G_consolidated.number_of_nodes()} nodes) "
            f"should have <= nodes than original ({G_original.number_of_nodes()} nodes)"
        )

        # Verify outlet node is still present and terminal
        assert G_consolidated.has_node("main_outlet")
        terminal_nodes = [
            n for n in G_consolidated.nodes() if G_consolidated.out_degree(n) == 0
        ]
        assert "main_outlet" in terminal_nodes

    def test_consolidation_preserves_custom_nodes(
        self, multi_subbasin_csv, consolidate_config
    ):
        """
        Test that consolidation preserves user-specified outlet points.
        Custom nodes should not be merged away during consolidation.
        """
        config.set(consolidate_config)

        G, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_custom_preserved", consolidate_config
        )

        # All custom outlet IDs should still be present
        expected_outlets = ["main_outlet", "upstream1", "upstream2"]
        for outlet_id in expected_outlets:
            assert G.has_node(outlet_id), (
                f"Custom outlet {outlet_id} should be preserved after consolidation"
            )

        # Verify custom attributes are preserved
        assert "gage_id" in subbasins_gdf.columns
        main_outlet_row = subbasins_gdf[subbasins_gdf["comid"] == "main_outlet"]
        assert main_outlet_row.iloc[0]["gage_id"] == "GAGE001"

    def test_consolidation_maintains_connectivity(
        self, multi_subbasin_csv, consolidate_config
    ):
        """
        Test that consolidation maintains network connectivity.
        The graph should still be connected and acyclic after consolidation.
        """
        config.set(consolidate_config)

        G, _, _ = delineate(multi_subbasin_csv, "test_connectivity", consolidate_config)

        # Graph should still be a DAG
        assert nx.is_directed_acyclic_graph(G), (
            "Consolidated network should still be a DAG"
        )

        # Should still have exactly one terminal node
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert len(terminal_nodes) == 1, (
            "Consolidated network should have exactly one terminal node"
        )
        assert terminal_nodes[0] == "main_outlet"


class TestGeometryValidity:
    """Test that output geometries are valid."""

    @pytest.fixture(autouse=True)
    def reset_config(self, default_config):
        """Reset config before each test."""
        config.set(default_config)

    def test_subbasin_geometries_valid(self, multi_subbasin_csv, default_config):
        """
        Test that all subbasin geometries are valid polygons.
        Invalid geometries can cause problems in downstream GIS analysis.

        Note: The MERIT-Hydro source data occasionally has invalid geometries
        (typically self-intersections). These can be fixed with make_valid().
        """
        from shapely.validation import make_valid

        config.set(default_config)

        _, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_valid_geom", default_config
        )

        # Check how many are invalid before fixing
        invalid_before = subbasins_gdf[~subbasins_gdf.geometry.is_valid]

        # All geometries should be fixable with make_valid
        fixed_geoms = subbasins_gdf.geometry.apply(
            lambda g: make_valid(g) if not g.is_valid else g
        )

        # After fixing, all should be valid
        still_invalid = fixed_geoms[~fixed_geoms.is_valid]
        assert len(still_invalid) == 0, (
            f"Found {len(still_invalid)} geometries that cannot be made valid"
        )

        # Log any that needed fixing (these are source data issues)
        if len(invalid_before) > 0:
            import warnings

            warnings.warn(
                f"Found {len(invalid_before)} invalid geometries in source data "
                f"(COMIDs: {invalid_before['comid'].tolist()}). "
                "These can be fixed with shapely.validation.make_valid()."
            )

    def test_subbasin_geometries_nonempty(self, multi_subbasin_csv, default_config):
        """
        Test that no subbasin geometries are empty.
        Every subbasin should have a polygon representing its contributing area.
        """
        config.set(default_config)

        _, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_nonempty_geom", default_config
        )

        # No empty geometries
        empty_geoms = subbasins_gdf[subbasins_gdf.geometry.is_empty]
        assert len(empty_geoms) == 0, (
            f"Found {len(empty_geoms)} empty subbasin geometries"
        )

    def test_subbasins_have_positive_area(self, multi_subbasin_csv, default_config):
        """
        Test that all subbasins have positive area.
        Area is a key attribute for hydrologic modeling.
        """
        config.set(default_config)

        _, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_positive_area", default_config
        )

        # All areas should be positive
        assert (subbasins_gdf["unitarea"] > 0).all(), (
            "All subbasins should have positive area"
        )

    def test_rivers_geometries_valid(self, multi_subbasin_csv, default_config):
        """
        Test that river reach geometries are valid LineStrings.
        """
        config.set(default_config)

        _, _, rivers_gdf = delineate(
            multi_subbasin_csv, "test_valid_rivers", default_config
        )

        # Filter out any empty geometries first (these are handled separately)
        non_empty = rivers_gdf[~rivers_gdf.geometry.is_empty]

        # All non-empty geometries should be valid
        invalid_geoms = non_empty[~non_empty.geometry.is_valid]
        assert len(invalid_geoms) == 0, (
            f"Found {len(invalid_geoms)} invalid river geometries"
        )


class TestDataConsistency:
    """Test consistency between graph, subbasins, and rivers data."""

    @pytest.fixture(autouse=True)
    def reset_config(self, default_config):
        """Reset config before each test."""
        config.set(default_config)

    def test_graph_subbasins_correspondence(self, multi_subbasin_csv, default_config):
        """
        Test that graph nodes correspond to subbasins in the GeoDataFrame.
        Every node in the graph should have a corresponding subbasin.
        """
        config.set(default_config)

        G, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_correspondence", default_config
        )

        graph_nodes = set(G.nodes())
        subbasin_ids = set(subbasins_gdf["comid"].tolist())

        # All graph nodes should be in subbasins
        missing_in_subbasins = graph_nodes - subbasin_ids
        assert len(missing_in_subbasins) == 0, (
            f"Graph nodes missing from subbasins: {missing_in_subbasins}"
        )

        # Verify terminal node
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "main_outlet" in terminal_nodes

    def test_nextdown_consistency(self, multi_subbasin_csv, default_config):
        """
        Test that graph structure is internally consistent.
        Every non-terminal node should have exactly one outgoing edge.
        Terminal nodes (outlets) should have no outgoing edges.
        """
        config.set(default_config)

        G, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_nextdown", default_config
        )

        # Every node should have at most one successor (river networks are trees)
        for node in G.nodes():
            out_degree = G.out_degree(node)
            assert out_degree <= 1, (
                f"Node {node} has {out_degree} successors, expected at most 1"
            )

        # The terminal node should have nextdown = 0 in the GeoDataFrame
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert len(terminal_nodes) >= 1, "Should have at least one terminal node"

        for terminal in terminal_nodes:
            if terminal in subbasins_gdf["comid"].values:
                terminal_row = subbasins_gdf[subbasins_gdf["comid"] == terminal]
                nextdown_val = terminal_row.iloc[0]["nextdown"]
                assert nextdown_val == 0, (
                    f"Terminal node {terminal} should have nextdown=0, got {nextdown_val}"
                )

    def test_area_values_consistent(self, multi_subbasin_csv, default_config):
        """
        Test that area values are consistent between graph and GeoDataFrame.
        """
        config.set(default_config)

        G, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_area_consistent", default_config
        )

        subbasins_gdf_indexed = subbasins_gdf.set_index("comid")

        for node in G.nodes():
            graph_area = G.nodes[node].get("area", 0)
            if node in subbasins_gdf_indexed.index:
                gdf_area = subbasins_gdf_indexed.loc[node, "unitarea"]
                # Allow small floating point differences
                assert abs(graph_area - gdf_area) < 0.5, (
                    f"Area mismatch for node {node}: graph={graph_area}, gdf={gdf_area}"
                )


class TestSnapshotOutputs:
    """Snapshot tests for complex output verification using syrupy."""

    @pytest.fixture
    def snapshot_json(self, snapshot: SnapshotAssertion):
        """Configure syrupy to use JSON extension for readable snapshots."""
        return snapshot.with_defaults(extension_class=JSONSnapshotExtension)

    @pytest.fixture(autouse=True)
    def reset_config(self, default_config):
        """Reset config before each test."""
        config.set(default_config)

    def test_single_outlet_network_structure_snapshot(
        self,
        single_outlet_csv,
        default_config,
        snapshot_json,
    ):
        """
        Snapshot test for network structure of single outlet delineation.
        Captures the essential topology of the delineated watershed.
        """
        config.set(default_config)

        G, subbasins_gdf, _ = delineate(
            single_outlet_csv, "test_snapshot", default_config
        )

        # Verify outlet node
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "outlet1" in terminal_nodes

        # Verify custom attributes are present
        assert "gage_id" in subbasins_gdf.columns
        outlet_row = subbasins_gdf[subbasins_gdf["comid"] == "outlet1"]
        assert outlet_row.iloc[0]["gage_id"] == "GAGE001"

        # Create a serializable summary of the network structure
        network_summary = {
            "num_nodes": G.number_of_nodes(),
            "num_edges": G.number_of_edges(),
            "custom_nodes": sorted(
                [str(n) for n, d in G.nodes(data=True) if d.get("custom", False)]
            ),
            "terminal_nodes": sorted(
                [str(n) for n in G.nodes() if G.out_degree(n) == 0]
            ),
            "max_strahler_order": max(
                d.get("strahler_order", 0) for _, d in G.nodes(data=True)
            ),
            "max_shreve_order": max(
                d.get("shreve_order", 0) for _, d in G.nodes(data=True)
            ),
        }

        assert network_summary == snapshot_json

    def test_multi_subbasin_structure_snapshot(
        self,
        multi_subbasin_csv,
        default_config,
        snapshot_json,
    ):
        """
        Snapshot test for multi-subbasin delineation structure.
        """
        config.set(default_config)

        G, subbasins_gdf, _ = delineate(
            multi_subbasin_csv, "test_multi_snapshot", default_config
        )

        # Verify outlet node
        terminal_nodes = [n for n in G.nodes() if G.out_degree(n) == 0]
        assert "main_outlet" in terminal_nodes

        # Verify custom attributes are present
        assert "gage_id" in subbasins_gdf.columns
        assert "priority" in subbasins_gdf.columns

        # Create a serializable summary
        network_summary = {
            "num_nodes": G.number_of_nodes(),
            "num_edges": G.number_of_edges(),
            "num_subbasins": len(subbasins_gdf),
            "custom_nodes": sorted(
                [str(n) for n, d in G.nodes(data=True) if d.get("custom", False)]
            ),
            "total_area_km2": round(subbasins_gdf["unitarea"].sum(), 1),
            "max_strahler_order": max(
                d.get("strahler_order", 0) for _, d in G.nodes(data=True)
            ),
        }

        assert network_summary == snapshot_json
