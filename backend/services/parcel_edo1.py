"""Crea la malla métrica y carga los forzamientos del EDO 1."""

from datetime import datetime, timedelta, timezone
import json
import math
from threading import Lock
from time import monotonic, sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CELL_M = 30
MAX_CELLS = 500
POWER_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
SRTM_URL = "https://api.opentopodata.org/v1/srtm30m"
POWER_PARAMETERS = ("T2M", "ALLSKY_SFC_SW_DWN", "RH2M")
SRTM_LOCK = Lock()
last_srtm_call = 0.0


class ParcelDataError(RuntimeError):
    pass


def build_grid(geometry):
    from pyproj import CRS, Transformer
    from shapely import transform
    from shapely.geometry import MultiPolygon, box, mapping, shape

    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Selecciona un terreno con un contorno poligonal.")
    try:
        parcel = shape(geometry)
    except (TypeError, ValueError, AttributeError, IndexError) as exc:
        raise ValueError("Las coordenadas de la parcela no son válidas.") from exc
    if parcel.is_empty or not parcel.is_valid:
        raise ValueError("Corrige el contorno de la parcela antes de simular.")
    west, south, east, north = parcel.bounds
    if not (-180 <= west < east <= 180 and -56 < south < north < 60 and east - west < 180):
        raise ValueError("La parcela está fuera de la cobertura compatible de SRTM.")

    center = parcel.centroid
    if not parcel.covers(center):
        center = parcel.representative_point()
    lon, lat = center.x, center.y
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m")
    project = Transformer.from_crs("EPSG:4326", local, always_xy=True).transform
    unproject = Transformer.from_crs(local, "EPSG:4326", always_xy=True).transform
    footprint = transform(parcel, project, interleaved=False)
    left, bottom, right, top = footprint.bounds
    cols, rows = math.ceil((right - left) / CELL_M), math.ceil((top - bottom) / CELL_M)
    if cols * rows > MAX_CELLS * 20 or footprint.area > MAX_CELLS * CELL_M ** 2:
        raise ValueError(f"La parcela supera el límite de {MAX_CELLS} celdas de 30 m.")

    cells = []
    samples = {}
    for row in range(rows):
        for col in range(cols):
            x, y = left + col * CELL_M, bottom + row * CELL_M
            square = box(x, y, x + CELL_M, y + CELL_M)
            clipped = square.intersection(footprint)
            if clipped.area <= 0:
                continue
            if clipped.geom_type == "GeometryCollection":
                clipped = MultiPolygon([part for part in clipped.geoms if part.geom_type == "Polygon"])
            point = square.centroid
            if not clipped.covers(point):
                point = clipped.representative_point()
            cell_id = f"{row}_{col}"
            cell_lon, cell_lat = unproject(point.x, point.y)
            cells.append({
                "cell_id": cell_id,
                "longitude": cell_lon,
                "latitude": cell_lat,
                "area_m2": clipped.area,
                "geometry": mapping(transform(clipped, unproject, interleaved=False)),
            })
            half = CELL_M / 2
            samples[cell_id] = [
                (cell_lon, cell_lat),
                unproject(point.x - half, point.y),
                unproject(point.x + half, point.y),
                unproject(point.x, point.y - half),
                unproject(point.x, point.y + half),
            ]
            if len(cells) > MAX_CELLS:
                raise ValueError(f"La parcela supera el límite de {MAX_CELLS} celdas de 30 m.")
    return cells, samples, (lon, lat)


def read_json(request):
    with urlopen(request, timeout=12) as response:
        return json.load(response)


def load_power(longitude, latitude, latest_day):
    params = {
        "parameters": ",".join(POWER_PARAMETERS),
        "community": "RE",
        "longitude": longitude,
        "latitude": latitude,
        "time-standard": "LST",
        "format": "JSON",
    }
    try:
        # Las series meteorológicas y solares pueden tener distintos retrasos.
        for first_offset, last_offset in ((0, 44), (45, 364)):
            start = latest_day - timedelta(days=last_offset)
            end = latest_day - timedelta(days=first_offset)
            params.update(start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
            response = read_json(f"{POWER_URL}?{urlencode(params)}")
            data = response["properties"]["parameter"]
            fill = response["header"]["fill_value"]
            for offset in range(first_offset, last_offset + 1):
                day = latest_day - timedelta(days=offset)
                hours = [f"{day:%Y%m%d}{hour:02d}" for hour in range(24)]
                series = {
                    key: {hour: float(data.get(key, {}).get(hour, fill)) for hour in hours}
                    for key in POWER_PARAMETERS
                }
                if all(math.isfinite(value) and value != fill for values in series.values() for value in values.values()):
                    return day, series, radiation_uses_mj(response)
        raise ValueError("Serie incompleta")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ParcelDataError("NASA POWER no devolvió las 24 horas requeridas para la simulación.") from exc


def radiation_uses_mj(response):
    units = response["parameters"]["ALLSKY_SFC_SW_DWN"]["units"].lower()
    units = units.replace(" ", "").replace("^", "").replace("²", "2")
    if units in {"w/m2", "wh/m2", "wh/m2/hour", "w-hr/m2"}:
        return False
    if units in {"mj/m2", "mj/m2/hr", "mj/m2/hour"}:
        return True
    raise ValueError("Unidad de radiación desconocida")


def load_elevations(points):
    global last_srtm_call
    # Redondear también permite reutilizar las muestras compartidas entre celdas.
    locations = list(dict.fromkeys(f"{lat:.7f},{lon:.7f}" for lon, lat in points))
    heights = {}
    try:
        for offset in range(0, len(locations), 100):
            batch = locations[offset:offset + 100]
            body = urlencode({"locations": "|".join(batch), "interpolation": "bilinear"}).encode()
            with SRTM_LOCK:
                sleep(max(0, 1.05 - (monotonic() - last_srtm_call)))
                last_srtm_call = monotonic()
                data = read_json(Request(SRTM_URL, data=body))
            results = data["results"]
            if data["status"] != "OK" or len(results) != len(batch):
                raise ValueError("Respuesta incompleta")
            for location, result in zip(batch, results):
                height = float(result["elevation"])
                if not math.isfinite(height):
                    raise ValueError("Elevación inválida")
                heights[location] = height
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ParcelDataError("SRTM no devolvió elevaciones válidas para toda la parcela.") from exc
    return [heights[f"{lat:.7f},{lon:.7f}"] for lon, lat in points]


def _format_hourly_t2m_blocks(t2m_series):
    """Agrupa las 24 horas de T2M en filas de 6 horas con etiqueta clara."""
    items = [f"{stamp[-2:]}:00 = {temp:5.2f} °C" for stamp, temp in sorted(t2m_series.items())]
    return [
        "      " + " | ".join(items[idx:idx + 6])
        for idx in range(0, len(items), 6)
    ]


def log_parcel_telemetry(day, reference, series, ref_altitude_m, result):
    """Imprime en la consola del servidor un reporte ordenado con el nombre de cada valor."""
    t2m_series = series.get("T2M", {})
    cells = result.get("cells", [])
    if not t2m_series or not cells:
        return

    temps = list(t2m_series.values())
    rads = list(series.get("ALLSKY_SFC_SW_DWN", {}).values())
    rhs = list(series.get("RH2M", {}).values())
    altitudes = [cell["altitude_m"] for cell in cells]
    slopes = [cell["slope_deg"] for cell in cells]
    total_area_m2 = sum(cell["area_m2"] for cell in cells)
    lon, lat = reference

    max_preview = 15
    cell_lines = [
        (
            f"      - Celda {cell.get('cell_id', idx + 1):>3}: "
            f"Latitud={cell['latitude']:.5f}° | "
            f"Longitud={cell['longitude']:.5f}° | "
            f"Altitud SRTM={cell['altitude_m']:.1f} m | "
            f"Pendiente={cell['slope_deg']:.2f}° | "
            f"Orientación={cell['aspect_deg']:.1f}° | "
            f"Temp. Dosel={cell['mean_canopy_temp']:.2f} °C"
        )
        for idx, cell in enumerate(cells[:max_preview])
    ]
    if len(cells) > max_preview:
        cell_lines.append(f"      ... (+{len(cells) - max_preview} celdas adicionales omitidas en vista rápida)")

    rad_unit = "MJ/m²/h" if result.get("is_radiation_mj_hr") else "W/m²"
    rad_summary = (
        f"Mínima={min(rads):.2f} {rad_unit} | Promedio={sum(rads) / len(rads):.2f} {rad_unit} | Máxima={max(rads):.2f} {rad_unit}"
        if rads else "Sin datos"
    )
    rh_summary = (
        f"Mínima={min(rhs):.1f} % | Promedio={sum(rhs) / len(rhs):.1f} % | Máxima={max(rhs):.1f} %"
        if rhs else "Sin datos"
    )

    lines = [
        "",
        "================================================================================",
        " REPORTE DEL SERVIDOR AGROPHASOR · NASA POWER + SRTM v3 + MOTOR EDO 1",
        "================================================================================",
        " [1] DATOS DE LA PARCELA Y CULTIVO",
        f"    • Cultivo evaluado                  : {result.get('crop', result.get('crop_id', 'papa'))} (id: {result.get('crop_id', 'papa')})",
        f"    • Latitud central de referencia     : {lat:.6f}°",
        f"    • Longitud central de referencia    : {lon:.6f}°",
        f"    • Cantidad de celdas (30x30 m)      : {len(cells)} celdas",
        f"    • Superficie total analizada        : {total_area_m2:.1f} m² ({total_area_m2 / 10000:.2f} ha)",
        f"    • Humedad radicular asumida         : {result.get('soil_water_mm', 50.0):.1f} mm",
        "--------------------------------------------------------------------------------",
        " [2] NASA POWER · VARIABLES CLIMÁTICAS",
        f"    • Fecha de consulta NASA POWER      : {day.isoformat()} (Hora Solar Local - LST)",
        f"    • Temp. del aire a 2m (T2M) Mínima  : {min(temps):.2f} °C",
        f"    • Temp. del aire a 2m (T2M) Promedio: {sum(temps) / len(temps):.2f} °C",
        f"    • Temp. del aire a 2m (T2M) Máxima  : {max(temps):.2f} °C",
        f"    • Radiación solar (ALLSKY_SFC_SW_DWN): {rad_summary}",
        f"    • Humedad relativa a 2m (RH2M)      : {rh_summary}",
        "    • Serie horaria de Temperatura del Aire (T2M - 24 horas):",
        *_format_hourly_t2m_blocks(t2m_series),
        "--------------------------------------------------------------------------------",
        " [3] SRTM v3 (OpenTopoData) · RELIEVE Y TOPOGRAFÍA",
        f"    • Altitud de referencia (centroide) : {ref_altitude_m:.2f} m s.n.m.",
        f"    • Altitud mínima de las celdas      : {min(altitudes):.2f} m s.n.m.",
        f"    • Altitud promedio de las celdas    : {sum(altitudes) / len(altitudes):.2f} m s.n.m.",
        f"    • Altitud máxima de las celdas      : {max(altitudes):.2f} m s.n.m.",
        f"    • Desnivel / Variación de altitud   : {max(altitudes) - min(altitudes):.2f} m",
        f"    • Pendiente mínima en parcela       : {min(slopes):.2f}°",
        f"    • Pendiente promedio en parcela     : {sum(slopes) / len(slopes):.2f}°",
        f"    • Pendiente máxima en parcela       : {max(slopes):.2f}°",
        "    • Detalle por celda (SRTM + EDO 1)  :",
        *cell_lines,
        "--------------------------------------------------------------------------------",
        " [4] RESULTADO TÉRMICO DEL DOSEL (EDO 1)",
        f"    • Temperatura media del dosel (lote): {result['lot_mean_temp']:.2f} °C",
        "================================================================================",
    ]
    print("\n".join(lines), flush=True)


def simulate_parcel(payload):
    from backend.models.crop_parameters import CROP_CATALOG
    from backend.services.simulation_service import SimulationService

    if not isinstance(payload, dict):
        raise ValueError("Envía la geometría de la parcela como JSON.")
    requested_crop = payload.get("crop_id", "papa")
    if not isinstance(requested_crop, str):
        raise ValueError("El identificador del cultivo debe ser texto.")
    crop_aliases = {"papa_canchan": "papa", "maiz_amilaceo": "maiz", "habas_verdes": "haba"}
    crop = crop_aliases.get(requested_crop, requested_crop)
    crop = crop if crop in CROP_CATALOG else "papa"
    water = float(payload.get("soil_water_mm", 50))
    if not math.isfinite(water) or water < 0:
        raise ValueError("La humedad radicular debe ser un valor no negativo en mm.")

    cells, samples, reference = build_grid(payload.get("geometry"))
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    day, series, radiation_in_mj = load_power(*reference, yesterday)
    points = [point for neighbors in samples.values() for point in neighbors]
    elevations = load_elevations([*points, reference])
    for index, cell in enumerate(cells):
        offset = index * 5
        altitude, west, east, south, north = elevations[offset:offset + 5]
        east_gradient = (east - west) / CELL_M
        north_gradient = (north - south) / CELL_M
        cell.update(
            altitude_m=altitude,
            slope_deg=math.degrees(math.atan(math.hypot(east_gradient, north_gradient))),
            aspect_deg=math.degrees(math.atan2(-east_gradient, -north_gradient)) % 360
            if east_gradient or north_gradient else 0.0,
        )
    result = SimulationService.run_field_simulation(
        series, cells, crop, soil_water_mm=water, ref_altitude_m=elevations[-1],
        is_radiation_mj_hr=radiation_in_mj,
    )
    for cell, thermal in zip(cells, result["cells"]):
        thermal.update(cell)
    area = sum(cell["area_m2"] for cell in cells)
    result["lot_mean_temp"] = round(sum(c["area_m2"] * c["mean_canopy_temp"] for c in result["cells"]) / area, 2)
    result.update(
        timestamps=list(series["T2M"]),
        date=day.isoformat(),
        time_standard="LST",
        cell_size_m=CELL_M,
        climate_source="NASA POWER",
        terrain_source="SRTM v3 (Open Topo Data)",
        crop_id=crop,
        reference_crop_used=crop == "papa" and requested_crop not in ("papa", "papa_canchan"),
    )
    log_parcel_telemetry(day, reference, series, elevations[-1], result)
    return result
