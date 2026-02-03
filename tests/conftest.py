"""
Pytest configuration and fixtures for watershed delineation tests.

This module sets up the environment variables needed to access remote hydrology data
and provides common fixtures used across test modules.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Set environment variables at module load time, before any imports
# These are required by upstream_delineator modules at import time
os.environ.setdefault(
    "CATCHMENT_PATH", "https://public-hydrology-data.upstream.tech/catchments"
)
os.environ.setdefault(
    "RIVER_PATH", "https://public-hydrology-data.upstream.tech/rivers"
)
os.environ.setdefault(
    "FLOW_DIR_PATH", "https://public-hydrology-data.upstream.tech/merit_flowdir.tif"
)
os.environ.setdefault(
    "ACCUM_PATH", "https://public-hydrology-data.upstream.tech/merit_accum.tif"
)
os.environ.setdefault(
    "MEGABASINS_PATH",
    "https://public-hydrology-data.upstream.tech/merit_basins_lvl2.gpkg",
)


@pytest.fixture(scope="session")
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def single_outlet_csv(tmp_path):
    """
    Create a CSV file with a single outlet point.
    Uses a location in Iceland (megabasin 27) for testing.
    Includes custom columns to verify they're passed through to the graph.
    """
    csv_path = tmp_path / "single_outlet.csv"
    csv_path.write_text(
        "id,lng,lat,name,outlet_id,gage_id,priority\n"
        "outlet1,-14.36201,65.50253,Lagarfljot River at Lagarfoss,outlet1,GAGE001,high\n"
    )
    return str(csv_path)


@pytest.fixture
def multi_subbasin_csv(tmp_path):
    """
    Create a CSV file with an outlet and upstream subbasin points.
    This tests the subbasin delineation capability.
    Includes custom columns (gage_id, priority) to verify they're passed through.
    """
    csv_path = tmp_path / "multi_subbasin.csv"
    csv_path.write_text(
        "id,lng,lat,name,outlet_id,gage_id,priority\n"
        "main_outlet,-14.36201,65.50253,Lagarfljot River at Lagarfoss,main_outlet,GAGE001,high\n"
        "upstream1,-15.0883,64.9839,Jokulsa I River at Fljotsdal Holl,main_outlet,GAGE002,medium\n"
        "upstream2,-14.533,65.14,Gringa Dam,main_outlet,GAGE003,low\n"
    )
    return str(csv_path)


@pytest.fixture
def headwater_outlet_csv(tmp_path):
    """
    Create a CSV file with a headwater outlet point.
    Headwater points are typically in leaf catchments with no upstream neighbors.
    """
    csv_path = tmp_path / "headwater.csv"
    # A point near the headwaters of a small stream in Iceland
    csv_path.write_text(
        "id,lng,lat,name,outlet_id,gage_id,priority\n"
        "headwater,-15.186,64.735,Lake Sauoarvatr outlet,headwater,GAGE_HW,high\n"
    )
    return str(csv_path)


@pytest.fixture
def disconnected_basins_csv(tmp_path):
    """
    Create a CSV file with two separate, disconnected watersheds.
    Each outlet_id defines a separate river system that should result
    in independent subgraphs in the final network.
    """
    csv_path = tmp_path / "disconnected_basins.csv"
    csv_path.write_text(
        "id,lng,lat,name,outlet_id,gage_id,priority\n"
        # First watershed - Lagarfljot system
        "basin1_outlet,-14.36201,65.50253,Lagarfljot River at Lagarfoss,basin1_outlet,GAGE_B1,high\n"
        "basin1_upstream,-14.533,65.14,Gringa Dam,basin1_outlet,GAGE_B1U,medium\n"
        # Second watershed - separate system near headwaters
        "basin2_outlet,-15.186,64.735,Lake Sauoarvatr outlet,basin2_outlet,GAGE_B2,high\n"
    )
    return str(csv_path)


@pytest.fixture
def default_config():
    """Default configuration for tests - minimal output, no plots."""
    return {
        "VERBOSE": False,
        "WRITE_OUTPUT": False,
        "PLOTS": False,
        "CONSOLIDATE": False,
        "NETWORK_DIAGRAMS": False,
        "SIMPLIFY": False,
    }


@pytest.fixture
def consolidate_config():
    """Configuration with consolidation enabled."""
    return {
        "VERBOSE": False,
        "WRITE_OUTPUT": False,
        "PLOTS": False,
        "CONSOLIDATE": True,
        "MAX_AREA": 500,
        "NETWORK_DIAGRAMS": False,
        "SIMPLIFY": False,
    }
