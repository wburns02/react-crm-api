"""
Open-Meteo Weather Service

Fetches current weather conditions and 7-day precipitation history
for septic inspection reports. Free API, no key required.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL = 600  # 10 minutes
DEFAULT_LAT = 29.8833  # San Marcos, TX
DEFAULT_LON = -97.9414

# WMO Weather Code → human-readable condition
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


class WeatherService:
    """Fetches weather data from Open-Meteo for inspection reports."""

    def __init__(self):
        self._cache: dict[str, tuple[float, dict]] = {}

    def _cache_key(self, lat: float, lon: float) -> str:
        return f"{round(lat, 2)}:{round(lon, 2)}"

    def _get_cached(self, lat: float, lon: float) -> Optional[dict]:
        key = self._cache_key(lat, lon)
        if key in self._cache:
            expires_at, data = self._cache[key]
            if time.time() < expires_at:
                return data
            del self._cache[key]
        return None

    def _set_cached(self, lat: float, lon: float, data: dict):
        key = self._cache_key(lat, lon)
        self._cache[key] = (time.time() + CACHE_TTL, data)

    async def fetch_weather(
        self,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        gps_source: str = "default",
    ) -> dict:
        """Fetch current weather + 7-day history. Returns dict for JSON storage."""
        lat = latitude or DEFAULT_LAT
        lon = longitude or DEFAULT_LON

        cached = self._get_cached(lat, lon)
        if cached:
            logger.info(f"Weather cache hit for {lat},{lon}")
            return cached

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                current_resp = await client.get(OPEN_METEO_BASE, params={
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                })
                current_resp.raise_for_status()
                current_data = current_resp.json()

                history_resp = await client.get(OPEN_METEO_BASE, params={
                    "latitude": lat, "longitude": lon,
                    "past_days": 7,
                    "daily": "precipitation_sum,rain_sum,precipitation_hours,weather_code,temperature_2m_max,temperature_2m_min",
                    "temperature_unit": "fahrenheit",
                    "precipitation_unit": "inch",
                    "forecast_days": 0,
                })
                history_resp.raise_for_status()
                history_data = history_resp.json()

            # Parse current conditions
            c = current_data.get("current", {})
            weather_code = c.get("weather_code", 0)
            current = {
                "temperature_f": round(c.get("temperature_2m", 0), 1),
                "feels_like_f": round(c.get("apparent_temperature", 0), 1),
                "humidity_pct": round(c.get("relative_humidity_2m", 0), 1),
                "precipitation_in": round(c.get("precipitation", 0), 2),
                "wind_speed_mph": round(c.get("wind_speed_10m", 0), 1),
                "condition": WEATHER_CODES.get(weather_code, f"Code {weather_code}"),
                "weather_code": weather_code,
            }

            # Parse 7-day history
            daily = history_data.get("daily", {})
            dates = daily.get("time", [])
            daily_history = []
            notable_events = []
            total_precip = 0.0

            for i, date_str in enumerate(dates):
                precip = round((daily.get("precipitation_sum") or [0] * len(dates))[i] or 0, 2)
                rain = round((daily.get("rain_sum") or [0] * len(dates))[i] or 0, 2)
                precip_hours = round((daily.get("precipitation_hours") or [0] * len(dates))[i] or 0, 1)
                wcode = (daily.get("weather_code") or [0] * len(dates))[i] or 0
                high = round((daily.get("temperature_2m_max") or [0] * len(dates))[i] or 0, 1)
                low = round((daily.get("temperature_2m_min") or [0] * len(dates))[i] or 0, 1)

                total_precip += precip
                daily_history.append({
                    "date": date_str,
                    "precip_in": precip,
                    "rain_in": rain,
                    "precip_hours": precip_hours,
                    "high_f": high,
                    "low_f": low,
                    "condition": WEATHER_CODES.get(wcode, f"Code {wcode}"),
                    "weather_code": wcode,
                })

                # Flag notable events
                day_label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d")
                if precip >= 0.5:
                    notable_events.append(f"Heavy rain ({precip} in) on {day_label}")
                elif wcode >= 95:
                    notable_events.append(f"Thunderstorms on {day_label}")
                elif wcode in (71, 73, 75, 77):
                    notable_events.append(f"Snow on {day_label}")

            result = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "gps_source": gps_source,
                "latitude": lat,
                "longitude": lon,
                "current": current,
                "daily_history": daily_history,
                "seven_day_total_precip_in": round(total_precip, 2),
                "notable_events": notable_events,
            }

            self._set_cached(lat, lon, result)
            logger.info(f"Weather fetched for {lat},{lon}: {current['condition']}, 7-day precip: {total_precip:.2f} in")
            return result

        except Exception as e:
            logger.warning(f"Weather fetch failed for {lat},{lon}: {e}")
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "gps_source": gps_source,
                "latitude": lat,
                "longitude": lon,
                "current": None,
                "daily_history": [],
                "seven_day_total_precip_in": 0,
                "notable_events": [],
                "error": str(e),
            }


# Singleton
weather_service = WeatherService()
