"""Land / water test for the Strait of Hormuz region.

Answers "is this lon/lat on land?" using an even-odd ray cast over Natural Earth
1:10m land polygons, accelerated by bucketing each polygon edge into the latitude
bands it spans. Standard library only - no project dependency is added.

Data source
-----------
Natural Earth 1:10m Physical Vectors - Land (public domain)
  reference/ne_10m_land.geojson
  https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_land.geojson
  sha256 1ac90796408bc6ad6911d69448485d3c4dbf2190370080368a09976e1c9f7416

Precision caveat
----------------
1:10m geometry is a cartographic product generalised for display at roughly
1:10,000,000 scale. Near-shore accuracy in this region is on the order of a few
hundred metres to about one kilometre. Breakwaters, reclaimed land, quay walls,
very small islets and near-shore anchorages are simplified or absent. This tool
is adequate for screening "does the centreline cross obvious land". It is NOT a
hydrographic survey and does NOT establish navigable-water safety.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

BAND_DEG = 0.01
LONG_EDGE_BANDS = 400


class LandChecker:
    """Land/water queries over prebuilt Natural Earth land polygons."""

    def __init__(self, rings: list[list[list[float]]], bbox=None):
        self.rings = rings
        self.bbox = bbox
        self.band_deg = BAND_DEG
        self._bands: dict[int, list[tuple]] = {}
        self._long_edges: list[tuple] = []
        self._built = False

    # ---------- construction ----------
    @classmethod
    def from_geojson(cls, path: Path) -> "LandChecker":
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        rings: list[list[list[float]]] = []
        for feature in doc["features"]:
            geom = feature["geometry"]
            polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            for poly in polys:
                # even-odd parity is computed per ring; holes just flip parity again
                for ring in poly:
                    rings.append([[float(p[0]), float(p[1])] for p in ring])
        return cls(rings)

    @classmethod
    def from_cache(cls, path: Path) -> "LandChecker":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(payload["rings"])

    def save_cache(self, path: Path) -> dict:
        Path(path).write_text(
            json.dumps({"band_deg": self.band_deg, "ring_count": len(self.rings), "rings": self.rings}),
            encoding="utf-8",
        )
        return {"ring_count": len(self.rings)}

    def build(self) -> dict:
        band = self.band_deg
        edge_total = 0
        for ring in self.rings:
            n = len(ring)
            if n < 3:
                continue
            for i in range(n):
                ax, ay = ring[i][0], ring[i][1]
                bx, by = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
                if ay == by:
                    edge_total += 1
                    continue
                lo = int(math.floor(min(ay, by) / band))
                hi = int(math.floor(max(ay, by) / band))
                if hi - lo > LONG_EDGE_BANDS:
                    self._long_edges.append((ax, ay, bx, by))
                else:
                    for b in range(lo, hi + 1):
                        self._bands.setdefault(b, []).append((ax, ay, bx, by))
                edge_total += 1
        self._built = True
        return {
            "rings": len(self.rings),
            "edges": edge_total,
            "lat_bands": len(self._bands),
            "long_edges": len(self._long_edges),
            "band_deg": band,
        }

    # ---------- query ----------
    def is_land(self, longitude: float, latitude: float) -> bool:
        if not self._built:
            raise RuntimeError("call build() first")
        band = int(math.floor(latitude / self.band_deg))
        crossings = 0
        lon = longitude
        lat = latitude
        for ax, ay, bx, by in self._bands.get(band, ()):
            if (ay > lat) != (by > lat):
                if lon < (bx - ax) * (lat - ay) / (by - ay) + ax:
                    crossings += 1
        for ax, ay, bx, by in self._long_edges:
            if (ay > lat) != (by > lat):
                if lon < (bx - ax) * (lat - ay) / (by - ay) + ax:
                    crossings += 1
        return crossings % 2 == 1

    # ---------- route helper ----------
    def check_route(self, waypoints, sample_km: float = 0.25,
                    lateral_offsets_km=(0.0, -1.0, 1.0, -2.0, 2.0, -3.0, 3.0)) -> dict:
        """Sample a polyline and verify the centre-line AND its lateral offsets are water.

        Lateral offsets matter because generated ships are spread either side of the
        centre-line; a centre-line that merely grazes the coast is not good enough.
        """
        def haversine(a, b):
            lat1, lon1 = math.radians(a[0]), math.radians(a[1])
            lat2, lon2 = math.radians(b[0]), math.radians(b[1])
            h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
            return 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(h)))

        def bearing(a, b):
            lat1, lat2 = math.radians(a[0]), math.radians(b[0])
            dlon = math.radians(b[1] - a[1])
            x = math.sin(dlon) * math.cos(lat2)
            y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
            return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0

        def shift(lat, lon, heading_deg, offset_km):
            starboard = math.radians((heading_deg + 90.0) % 360.0)
            angular = offset_km / 6371.0088
            lat1, lon1 = math.radians(lat), math.radians(lon)
            lat2 = math.asin(math.sin(lat1) * math.cos(angular)
                             + math.cos(lat1) * math.sin(angular) * math.cos(starboard))
            lon2 = lon1 + math.atan2(math.sin(starboard) * math.sin(angular) * math.cos(lat1),
                                     math.cos(angular) - math.sin(lat1) * math.sin(lat2))
            return math.degrees(lat2), ((math.degrees(lon2) + 540.0) % 360.0) - 180.0

        total = 0.0
        hits = []
        samples = 0
        minimum_margin_km = None
        for i in range(len(waypoints) - 1):
            a, b = waypoints[i], waypoints[i + 1]
            seg = haversine(a, b)
            heading = bearing(a, b)
            steps = max(2, int(seg / sample_km))
            for s in range(steps + 1):
                t = s / steps
                lat = a[0] + (b[0] - a[0]) * t
                lon = a[1] + (b[1] - a[1]) * t
                samples += 1
                for offset in lateral_offsets_km:
                    test_lat, test_lon = (lat, lon) if offset == 0 else shift(lat, lon, heading, offset)
                    if self.is_land(test_lon, test_lat):
                        hits.append({"seg": i, "lat": round(test_lat, 5), "lon": round(test_lon, 5),
                                     "offset_km": offset, "route_km": round(total + seg * t, 2)})
                        if offset == 0:
                            minimum_margin_km = 0.0
            total += seg
        return {
            "length_km": round(total, 2),
            "samples": samples,
            "lateral_offsets_checked_km": list(lateral_offsets_km),
            "land_samples": len(hits),
            "first_land_samples": hits[:8],
            "clean": len(hits) == 0,
        }


    # ---------- safety-margin variant ----------
    def is_water_with_margin(self, longitude: float, latitude: float, margin_km: float = 0.5) -> bool:
        """True when the point and a small ring around it are all water.

        Used as the placement safety net: a point that is technically water but
        only metres from the reference coastline is treated as unusable.
        """
        if self.is_land(longitude, latitude):
            return False
        if margin_km <= 0:
            return True
        for bearing_deg in range(0, 360, 45):
            starboard = math.radians(bearing_deg)
            angular = margin_km / 6371.0088
            lat1, lon1 = math.radians(latitude), math.radians(longitude)
            lat2 = math.asin(math.sin(lat1) * math.cos(angular)
                             + math.cos(lat1) * math.sin(angular) * math.cos(starboard))
            lon2 = lon1 + math.atan2(math.sin(starboard) * math.sin(angular) * math.cos(lat1),
                                     math.cos(angular) - math.sin(lat1) * math.sin(lat2))
            if self.is_land(((math.degrees(lon2) + 540.0) % 360.0) - 180.0, math.degrees(lat2)):
                return False
        return True


PROBES = [
    ("伊朗内陆", 54.37, 30.50, True),
    ("波斯湾中部", 51.50, 27.00, False),
    ("波斯湾北部", 49.50, 28.50, False),
    ("海峡主航道附近", 56.45, 26.55, False),
    ("海峡南侧水道", 56.45, 26.32, False),
    ("穆桑代姆半岛内陆", 56.20, 26.10, True),
    ("盖什姆岛", 55.90, 26.85, True),
    ("阿曼湾", 57.50, 25.60, False),
    ("阿拉伯海", 58.50, 24.00, False),
    ("迪拜市区", 55.30, 25.27, True),
    ("杰贝阿里港区", 55.06, 25.01, True),
    ("阿布穆萨岛", 55.03, 25.87, True),
    ("大通布岛", 55.30, 26.26, True),
    ("基什岛", 54.00, 26.55, True),
    ("富查伊拉近岸", 56.40, 25.15, False),
    ("阿曼内陆", 56.00, 24.00, True),
    ("伊朗沿岸恰巴哈尔", 60.62, 25.29, True),
]


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    geo = here.parent / "reference" / "ne_10m_land.geojson"

    checker = LandChecker.from_geojson(geo)
    print("built:", checker.build())

    print("\n判定探针（期望 vs 实测）：")
    failures = 0
    for label, lon, lat, expect in PROBES:
        got = checker.is_land(lon, lat)
        mark = "OK " if got == expect else "MISMATCH"
        if got != expect:
            failures += 1
        print(f"  {mark:9s} {label:16s} lon={lon:7.2f} lat={lat:6.2f} 期望={'陆地' if expect else '水域'} 实测={'陆地' if got else '水域'}")
    print(f"\n探针不匹配数：{failures}/{len(PROBES)}")
