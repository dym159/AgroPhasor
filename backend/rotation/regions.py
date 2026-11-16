"""Department boundary lookup for Peru based on geoBoundaries ADM1 data."""

from functools import lru_cache
import json
from pathlib import Path
from typing import List, Optional, Tuple

from shapely.geometry import Point, shape
from shapely.prepared import prep

_GEOJSON_PATH = Path(__file__).resolve().parents[1] / "data" / "peru_departments.geojson"


@lru_cache(maxsize=1)
def _load_departments() -> Tuple[Tuple[str, object, object], ...]:
    """Load, prepare, and cache Peruvian department geometries with bounding boxes."""
    if not _GEOJSON_PATH.is_file():
        return ()
    data = json.loads(_GEOJSON_PATH.read_text(encoding="utf-8"))
    loaded: List[Tuple[str, object, object]] = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        name = str(props.get("shapeName") or props.get("name") or "").strip()
        geom_data = feature.get("geometry")
        if not name or not geom_data:
            continue
        geom = shape(geom_data)
        loaded.append((name, geom.bounds, prep(geom)))
    loaded.sort(key=lambda item: item[0])
    return tuple(loaded)


def department_names() -> List[str]:
    """Return sorted department names available in the boundary dataset."""
    return [name for name, _, _ in _load_departments()]


def department_at(longitude: float, latitude: float) -> Optional[str]:
    """Return the Peruvian department name covering (longitude, latitude), or None."""
    point = Point(longitude, latitude)
    for name, (minx, miny, maxx, maxy), prepared_geom in _load_departments():
        if not (minx <= longitude <= maxx and miny <= latitude <= maxy):
            continue
        if prepared_geom.covers(point):
            return name
    return None
