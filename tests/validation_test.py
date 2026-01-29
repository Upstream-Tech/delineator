"""
Tests for input validation and error handling.

These tests verify that the library correctly validates inputs and
produces appropriate error messages for invalid data.
"""

import pandas as pd
import pytest

from upstream_delineator.delineator_utils.util import find_repeated_elements, validate


class TestValidateFunction:
    """Test the validate function for CSV input validation."""

    def test_validate_valid_input(self):
        """Test that valid input passes validation."""
        df = pd.DataFrame(
            {
                "id": ["outlet1", "point2"],
                "lat": [65.5, 64.9],
                "lng": [-14.3, -15.0],
                "outlet_id": ["outlet1", "outlet1"],
            }
        )

        result = validate(df)
        assert result is True

    def test_validate_missing_id_column(self):
        """Test that missing 'id' column raises ValueError."""
        df = pd.DataFrame(
            {
                "lat": [65.5],
                "lng": [-14.3],
                "outlet_id": ["outlet1"],
            }
        )

        with pytest.raises(ValueError, match="Missing column.*id"):
            validate(df)

    def test_validate_missing_lat_column(self):
        """Test that missing 'lat' column raises ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1"],
                "lng": [-14.3],
                "outlet_id": ["outlet1"],
            }
        )

        with pytest.raises(ValueError, match="Missing column.*lat"):
            validate(df)

    def test_validate_missing_lng_column(self):
        """Test that missing 'lng' column raises ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1"],
                "lat": [65.5],
                "outlet_id": ["outlet1"],
            }
        )

        with pytest.raises(ValueError, match="Missing column.*lng"):
            validate(df)

    def test_validate_missing_outlet_id_column(self):
        """Test that missing 'outlet_id' column raises ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1"],
                "lat": [65.5],
                "lng": [-14.3],
            }
        )

        with pytest.raises(ValueError, match="Missing column.*outlet_id"):
            validate(df)

    def test_validate_duplicate_ids(self):
        """Test that duplicate IDs raise ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1", "outlet1"],  # Duplicate!
                "lat": [65.5, 64.9],
                "lng": [-14.3, -15.0],
                "outlet_id": ["outlet1", "outlet1"],
            }
        )

        with pytest.raises(ValueError, match="unique"):
            validate(df)

    def test_validate_non_numeric_lat(self):
        """Test that non-numeric latitude raises ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1"],
                "lat": ["not_a_number"],
                "lng": [-14.3],
                "outlet_id": ["outlet1"],
            }
        )

        with pytest.raises(ValueError, match="lat.*not numeric"):
            validate(df)

    def test_validate_lat_too_low(self):
        """Test that latitude < -60 raises ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1"],
                "lat": [-70.0],  # Below -60 (MERIT-Hydro coverage limit)
                "lng": [-14.3],
                "outlet_id": ["outlet1"],
            }
        )

        with pytest.raises(ValueError, match="latitude.*greater than -60"):
            validate(df)

    def test_validate_lat_too_high(self):
        """Test that latitude > 85 raises ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1"],
                "lat": [90.0],  # Above 85 (MERIT-Hydro coverage limit)
                "lng": [-14.3],
                "outlet_id": ["outlet1"],
            }
        )

        with pytest.raises(ValueError, match="latitude.*less than 85"):
            validate(df)

    def test_validate_lng_too_low(self):
        """Test that longitude < -180 raises ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1"],
                "lat": [65.5],
                "lng": [-200.0],  # Below -180
                "outlet_id": ["outlet1"],
            }
        )

        with pytest.raises(ValueError, match="longitude.*greater than -180"):
            validate(df)

    def test_validate_lng_too_high(self):
        """Test that longitude > 180 raises ValueError."""
        df = pd.DataFrame(
            {
                "id": ["outlet1"],
                "lat": [65.5],
                "lng": [200.0],  # Above 180
                "outlet_id": ["outlet1"],
            }
        )

        with pytest.raises(ValueError, match="longitude.*less than 180"):
            validate(df)

    def test_validate_id_zero_not_allowed(self):
        """Test that id=0 is not allowed (reserved for ocean discharge)."""
        df = pd.DataFrame(
            {
                "id": ["0"],  # Reserved value
                "lat": [65.5],
                "lng": [-14.3],
                "outlet_id": ["0"],
            }
        )

        with pytest.raises(ValueError, match="id of 0 not allowed"):
            validate(df)

    def test_validate_outlet_id_must_reference_existing_id(self):
        """Test that outlet_id must reference an existing id in the CSV."""
        df = pd.DataFrame(
            {
                "id": ["point1"],
                "lat": [65.5],
                "lng": [-14.3],
                "outlet_id": ["nonexistent"],  # This id doesn't exist
            }
        )

        with pytest.raises(ValueError, match="outlet_id.*must reference id"):
            validate(df)


class TestFindRepeatedElements:
    """Test the find_repeated_elements utility function."""

    def test_no_repeats(self):
        """Test list with no repeated elements."""
        lst = [1, 2, 3, 4, 5]
        result = find_repeated_elements(lst)
        assert result == []

    def test_single_repeat(self):
        """Test list with one repeated element."""
        lst = [1, 2, 2, 3, 4]
        result = find_repeated_elements(lst)
        assert result == [2]

    def test_multiple_repeats(self):
        """Test list with multiple repeated elements."""
        lst = [1, 2, 2, 3, 3, 4]
        result = find_repeated_elements(lst)
        assert set(result) == {2, 3}

    def test_all_same(self):
        """Test list where all elements are the same."""
        lst = [5, 5, 5, 5]
        result = find_repeated_elements(lst)
        assert result == [5]

    def test_empty_list(self):
        """Test empty list returns empty list."""
        lst = []
        result = find_repeated_elements(lst)
        assert result == []

    def test_single_element(self):
        """Test single element list returns empty list."""
        lst = [42]
        result = find_repeated_elements(lst)
        assert result == []
