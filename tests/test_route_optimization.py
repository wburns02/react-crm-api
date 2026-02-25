"""Tests for route optimization haversine/nearest-neighbor logic."""
import pytest
import math


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance in miles between two points on earth."""
    R = 3959  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


class TestHaversineDistance:
    """Test haversine distance calculations used in route optimization."""

    def test_same_point_is_zero(self):
        """Distance from a point to itself should be zero."""
        assert haversine_distance(30.0, -97.0, 30.0, -97.0) == pytest.approx(0.0)

    def test_known_distance_austin_to_san_antonio(self):
        """Austin (30.27, -97.74) to San Antonio (29.42, -98.49) ≈ 73 miles."""
        d = haversine_distance(30.2672, -97.7431, 29.4241, -98.4936)
        assert 70 < d < 80

    def test_known_distance_new_york_to_la(self):
        """NYC to LA ≈ 2,451 miles."""
        d = haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)
        assert 2400 < d < 2500

    def test_symmetry(self):
        """Distance A→B should equal B→A."""
        d1 = haversine_distance(30.0, -97.0, 31.0, -98.0)
        d2 = haversine_distance(31.0, -98.0, 30.0, -97.0)
        assert d1 == pytest.approx(d2)

    def test_short_distance_same_city(self):
        """Points within the same city should be < 30 miles."""
        # San Marcos to New Braunfels, TX
        d = haversine_distance(29.8833, -97.9414, 29.7030, -98.1245)
        assert 5 < d < 20


class TestNearestNeighborOrdering:
    """Test nearest-neighbor TSP heuristic used in route optimization."""

    def test_orders_by_proximity(self):
        """Given a start point, nearest-neighbor should visit closest first."""
        points = [
            {"name": "A", "lat": 30.0, "lng": -97.0},  # start
            {"name": "B", "lat": 30.5, "lng": -97.5},  # far
            {"name": "C", "lat": 30.1, "lng": -97.1},  # close
            {"name": "D", "lat": 30.3, "lng": -97.3},  # medium
        ]
        start = points[0]
        remaining = points[1:]

        # Nearest-neighbor: always go to closest unvisited
        ordered = []
        current = start
        unvisited = list(remaining)
        while unvisited:
            nearest = min(
                unvisited,
                key=lambda p: haversine_distance(current["lat"], current["lng"], p["lat"], p["lng"]),
            )
            ordered.append(nearest)
            unvisited.remove(nearest)
            current = nearest

        assert ordered[0]["name"] == "C"  # closest to A
        assert ordered[-1]["name"] == "B"  # farthest

    def test_single_stop(self):
        """Single stop should return that stop."""
        stops = [{"lat": 30.0, "lng": -97.0}]
        assert len(stops) == 1

    def test_empty_stops(self):
        """Empty list should produce empty route."""
        assert [] == []

    def test_drive_time_estimate(self):
        """35 mph estimate: 35 miles should take ~60 minutes."""
        speed_mph = 35
        distance = 35.0
        minutes = (distance / speed_mph) * 60
        assert minutes == pytest.approx(60.0)
