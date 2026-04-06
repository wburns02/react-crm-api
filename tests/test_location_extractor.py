import pytest
import math
from unittest.mock import AsyncMock, patch
from app.services.location_extractor import LocationExtractor


@pytest.fixture
def extractor():
    return LocationExtractor(call_sid="CA_test_123", market_slug="nashville")


def test_extract_city_from_text(extractor):
    """Detects city names in transcript text."""
    result = extractor.extract_location_from_text("Yeah we're in Spring Hill")
    assert result is not None
    assert result["source"] == "transcript"
    assert abs(result["lat"] - 35.7512) < 0.05
    assert result["address_text"] == "Spring Hill"


def test_extract_city_case_insensitive(extractor):
    result = extractor.extract_location_from_text("I'm over in columbia right now")
    assert result is not None
    assert result["address_text"] == "Columbia"


def test_extract_full_address(extractor):
    """Detects street address patterns."""
    result = extractor.extract_location_from_text("We're at 1205 Hampshire Pike in Columbia")
    assert result is not None
    assert "Hampshire Pike" in result["address_text"] or "Columbia" in result["address_text"]


def test_extract_street_mention(extractor):
    """Detects 'on [Street] Pike/Road/Drive' patterns."""
    with patch.object(extractor, '_geocode_address', return_value={
        "lat": 35.62, "lng": -87.05, "address_text": "Bear Creek Pike", "source": "transcript"
    }):
        result = extractor.extract_location_from_text("out on Bear Creek Pike")
        assert result is not None
        assert "Bear Creek Pike" in result["address_text"]


def test_no_location_in_text(extractor):
    result = extractor.extract_location_from_text("I need my septic pumped as soon as possible")
    assert result is None


def test_extract_do_you_service_pattern(extractor):
    """Detects 'do you service [City]?' pattern."""
    result = extractor.extract_location_from_text("Do you service Spring Hill?")
    assert result is not None
    assert result["address_text"] == "Spring Hill"


def test_zone_included_in_result(extractor):
    result = extractor.extract_location_from_text("I'm in Columbia")
    assert result is not None
    assert result["zone"] in ("core", "extended", "outside")


def test_drive_time_included(extractor):
    result = extractor.extract_location_from_text("I'm in Franklin")
    assert result is not None
    assert "drive_minutes" in result
    assert isinstance(result["drive_minutes"], (int, float))
    assert result["drive_minutes"] > 0


def test_confidence_city_name(extractor):
    result = extractor.extract_location_from_text("I'm in Spring Hill")
    assert result is not None
    assert result["confidence"] == 0.7


def test_confidence_address(extractor):
    result = extractor.extract_location_from_text("We're at 1205 Hampshire Pike in Columbia")
    assert result is not None
    assert result["confidence"] >= 0.8


def test_dedup_same_location(extractor):
    """Second mention of same city doesn't produce a new result."""
    result1 = extractor.extract_location_from_text("I'm in Columbia")
    assert result1 is not None
    result2 = extractor.extract_location_from_text("Yeah, Columbia, near the square")
    assert result2 is None  # Deduped


def test_dedup_different_location(extractor):
    """Different city produces a new result even after previous detection."""
    result1 = extractor.extract_location_from_text("I'm in Columbia")
    assert result1 is not None
    result2 = extractor.extract_location_from_text("Actually closer to Spring Hill")
    assert result2 is not None  # Different location


def test_dedup_higher_confidence_replaces(extractor):
    """Higher confidence for same area replaces lower confidence."""
    result1 = extractor.extract_location_from_text("I'm in Columbia")
    assert result1 is not None
    assert result1["confidence"] == 0.7
    result2 = extractor.extract_location_from_text("1205 Hampshire Pike in Columbia")
    assert result2 is not None  # Higher confidence replaces
    assert result2["confidence"] >= 0.8


def test_haversine_distance():
    from app.services.location_extractor import haversine_distance
    # Columbia to Nashville ~ 45 miles
    dist = haversine_distance(35.6145, -87.0353, 36.1627, -86.7816)
    assert 38 < dist < 52


def test_drive_time_estimate():
    from app.services.location_extractor import estimate_drive_minutes
    # 35 miles at 35 mph = 60 minutes
    minutes = estimate_drive_minutes(35.0)
    assert abs(minutes - 60) < 1
