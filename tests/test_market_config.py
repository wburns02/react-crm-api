import pytest
from app.services.market_config import (
    get_market_by_area_code,
    get_market_by_slug,
    lookup_city,
    point_in_polygon,
    get_zone,
    DEFAULT_MARKET_SLUG,
)


def test_area_code_615_returns_nashville():
    market = get_market_by_area_code("615")
    assert market is not None
    assert market["slug"] == "nashville"
    assert "615" in market["area_codes"]


def test_area_code_629_returns_nashville():
    market = get_market_by_area_code("629")
    assert market is not None
    assert market["slug"] == "nashville"


def test_area_code_931_returns_nashville():
    market = get_market_by_area_code("931")
    assert market is not None
    assert market["slug"] == "nashville"


def test_area_code_737_returns_san_marcos():
    market = get_market_by_area_code("737")
    assert market is not None
    assert market["slug"] == "san_marcos"


def test_area_code_512_returns_san_marcos():
    market = get_market_by_area_code("512")
    assert market is not None
    assert market["slug"] == "san_marcos"


def test_unknown_area_code_returns_default():
    market = get_market_by_area_code("212")
    assert market is not None
    assert market["slug"] == DEFAULT_MARKET_SLUG


def test_get_market_by_slug():
    market = get_market_by_slug("nashville")
    assert market is not None
    assert market["name"] == "Nashville / Middle TN"


def test_lookup_city_columbia():
    result = lookup_city("Columbia", "nashville")
    assert result is not None
    assert abs(result["lat"] - 35.6145) < 0.05
    assert abs(result["lng"] - (-87.0353)) < 0.05


def test_lookup_city_spring_hill():
    result = lookup_city("Spring Hill", "nashville")
    assert result is not None
    assert abs(result["lat"] - 35.7512) < 0.05


def test_lookup_city_case_insensitive():
    result = lookup_city("spring hill", "nashville")
    assert result is not None


def test_lookup_city_unknown():
    result = lookup_city("Nonexistent City", "nashville")
    assert result is None


def test_point_in_polygon_inside():
    polygon = [
        (0.0, 0.0),
        (0.0, 10.0),
        (10.0, 10.0),
        (10.0, 0.0),
    ]
    assert point_in_polygon(5.0, 5.0, polygon) is True


def test_point_in_polygon_outside():
    polygon = [
        (0.0, 0.0),
        (0.0, 10.0),
        (10.0, 10.0),
        (10.0, 0.0),
    ]
    assert point_in_polygon(15.0, 5.0, polygon) is False


def test_get_zone_columbia_is_core():
    zone = get_zone(35.6145, -87.0353, "nashville")
    assert zone == "core"


def test_get_zone_nashville_is_extended():
    zone = get_zone(36.16, -86.78, "nashville")
    assert zone == "extended"


def test_get_zone_far_away_is_outside():
    zone = get_zone(40.0, -80.0, "nashville")
    assert zone == "outside"


def test_get_zone_no_polygons():
    zone = get_zone(29.88, -97.94, "san_marcos")
    assert zone == "outside"
