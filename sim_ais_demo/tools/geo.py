"""Pure-python geodesic and polyline helpers. Standard library only."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088
KM_PER_NAUTICAL_MILE = 1.852


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between (lat, lon) pairs."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def initial_bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Initial great-circle bearing from a to b, degrees true in [0, 360)."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def knots_to_km_per_second(knots: float) -> float:
    return knots * KM_PER_NAUTICAL_MILE / 3600.0


def km_per_second_to_knots(km_per_second: float) -> float:
    return km_per_second * 3600.0 / KM_PER_NAUTICAL_MILE


class Route:
    """Polyline with cumulative great-circle distance and offset-aware sampling."""

    def __init__(self, points: list[tuple[float, float]]):
        if len(points) < 2:
            raise ValueError("route needs at least two points")
        self.points = [(float(p[0]), float(p[1])) for p in points]
        self.cum = [0.0]
        for i in range(len(self.points) - 1):
            self.cum.append(self.cum[-1] + haversine_km(self.points[i], self.points[i + 1]))
        self.length_km = self.cum[-1]

    def point_at(self, distance_km: float) -> tuple[float, float]:
        """Position at a given along-track distance; clamped to the ends."""
        if distance_km <= 0:
            return self.points[0]
        if distance_km >= self.length_km:
            return self.points[-1]
        lo, hi = 0, len(self.cum) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if self.cum[mid] <= distance_km:
                lo = mid
            else:
                hi = mid
        seg = self.cum[hi] - self.cum[lo]
        ratio = 0.0 if seg <= 0 else (distance_km - self.cum[lo]) / seg
        a, b = self.points[lo], self.points[hi]
        return (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)

    def bearing_at(self, distance_km: float) -> float:
        """Along-track bearing, taken across a small window to stay smooth."""
        delta = 0.25
        a = self.point_at(max(0.0, distance_km - delta))
        b = self.point_at(min(self.length_km, distance_km + delta))
        if haversine_km(a, b) < 1e-9:
            return self.bearing_at(min(self.length_km, distance_km + 1.0))
        return initial_bearing_deg(a, b)


def offset_point(
    lat: float,
    lon: float,
    bearing_deg: float,
    offset_km: float,
) -> tuple[float, float]:
    """Move a point sideways: bearing_deg is the heading, offset is to starboard."""
    starboard = math.radians((bearing_deg + 90.0) % 360.0)
    angular = offset_km / EARTH_RADIUS_KM
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(starboard)
    )
    lon2 = lon1 + math.atan2(
        math.sin(starboard) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return (math.degrees(lat2), ((math.degrees(lon2) + 540.0) % 360.0) - 180.0)


def knot_hash(value: int, salt: int) -> float:
    """Deterministic pseudo-random float in [0, 1) - no dependency on random module state."""
    x = (value * 2654435761 + salt * 40503) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 2246822519) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 3266489917) & 0xFFFFFFFF
    x ^= x >> 16
    return x / 4294967296.0
