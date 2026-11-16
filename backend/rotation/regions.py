"""Local lookup of Peruvian departments for crop calendars."""

from functools import lru_cache
import json
from pathlib import Path

from shapely.geometry import Point, shape


@lru_cache(maxsize=1)
def departments():
    path = Path(__file__).resolve().parents[1] / "data" / "peru_departments.geojson"
    with path.open(encoding="utf-8") as source:
        features = json.load(source)["features"]
    names = {"Ancash": "Áncash", "El Callao": "Callao",
             "Municipalidad Metropolitana de Lima": "Lima"}
    return tuple((names.get(feature["properties"]["name"], feature["properties"]["name"]),
                  shape(feature["geometry"])) for feature in features)


def department_at(longitude, latitude):
    point = Point(longitude, latitude)
    return next((name for name, boundary in departments() if boundary.covers(point)), None)


def department_names():
    return sorted({name for name, _ in departments()}, key=str.casefold)
