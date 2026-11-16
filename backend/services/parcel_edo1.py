"""Simula las cinco EDO y deriva las salidas visuales de la parcela."""

from dataclasses import replace
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
REQUESTED_POWER_PARAMETERS = (*POWER_PARAMETERS, "PRECTOT")
POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
SRTM_LOCK = Lock()
last_srtm_call = 0.0


class ParcelDataError(RuntimeError):
    pass


def _build_grid_pure_python(geometry):
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Selecciona un terreno con un contorno poligonal.")
    coords_list = geometry.get("coordinates", [])
    if not coords_list:
        raise ValueError("Las coordenadas de la parcela están vacías.")
    ring = coords_list[0] if geometry.get("type") == "Polygon" else coords_list[0][0]
    lons = [float(c[0]) for c in ring]
    lats = [float(c[1]) for c in ring]
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)
    if not (-180 <= west < east <= 180 and -56 < south < north < 60 and east - west < 180):
        raise ValueError("La parcela está fuera de la cobertura compatible de SRTM.")

    center_lon = (west + east) / 2.0
    center_lat = (south + north) / 2.0
    lat_rad = math.radians(center_lat)
    m_per_deg_lat = 111132.95
    m_per_deg_lon = max(100.0, 111132.95 * math.cos(lat_rad))

    d_lon = CELL_M / m_per_deg_lon
    d_lat = CELL_M / m_per_deg_lat
    cols = max(1, math.ceil((east - west) / d_lon))
    rows = max(1, math.ceil((north - south) / d_lat))
    if cols * rows > MAX_CELLS * 20:
        raise ValueError(f"La parcela supera el límite de {MAX_CELLS} celdas de 30 m.")

    def point_in_poly(x, y):
        n = len(ring)
        inside = False
        p1x, p1y = ring[0]
        for i in range(1, n + 1):
            p2x, p2y = ring[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    cells = []
    samples = {}
    half_m = CELL_M / 2.0
    half_lon = half_m / m_per_deg_lon
    half_lat = half_m / m_per_deg_lat

    for r in range(rows):
        for c in range(cols):
            c_lon = west + (c + 0.5) * d_lon
            c_lat = south + (r + 0.5) * d_lat
            if point_in_poly(c_lon, c_lat) or (rows * cols <= 4):
                cell_id = f"{r}_{c}"
                cells.append({
                    "cell_id": cell_id,
                    "longitude": c_lon,
                    "latitude": c_lat,
                    "area_m2": CELL_M * CELL_M,
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [c_lon - half_lon, c_lat - half_lat],
                            [c_lon + half_lon, c_lat - half_lat],
                            [c_lon + half_lon, c_lat + half_lat],
                            [c_lon - half_lon, c_lat + half_lat],
                            [c_lon - half_lon, c_lat - half_lat]
                        ]]
                    }
                })
                samples[cell_id] = [
                    (c_lon, c_lat),
                    (c_lon - half_lon, c_lat),
                    (c_lon + half_lon, c_lat),
                    (c_lon, c_lat - half_lat),
                    (c_lon, c_lat + half_lat)
                ]
                if len(cells) > MAX_CELLS:
                    raise ValueError(f"La parcela supera el límite de {MAX_CELLS} celdas de 30 m.")

    if not cells:
        # Si el polígono es muy estrecho, incluir al menos la celda central
        cells.append({
            "cell_id": "0_0",
            "longitude": center_lon,
            "latitude": center_lat,
            "area_m2": CELL_M * CELL_M,
            "geometry": {"type": "Point", "coordinates": [center_lon, center_lat]}
        })
        samples["0_0"] = [
            (center_lon, center_lat),
            (center_lon - half_lon, center_lat),
            (center_lon + half_lon, center_lat),
            (center_lon, center_lat - half_lat),
            (center_lon, center_lat + half_lat)
        ]

    return cells, samples, (center_lon, center_lat)


def build_grid(geometry):
    try:
        from pyproj import CRS, Transformer
        from shapely import transform
        from shapely.geometry import MultiPolygon, box, mapping, shape
    except ImportError:
        return _build_grid_pure_python(geometry)

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
        "parameters": ",".join(REQUESTED_POWER_PARAMETERS),
        "community": "AG",
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
                series = {}
                for key in (*REQUESTED_POWER_PARAMETERS, "PRECTOTCORR"):
                    if key in data:
                        series[key] = {hour: float(data[key].get(hour, fill)) for hour in hours}
                    elif key in POWER_PARAMETERS:
                        series[key] = {hour: float(fill) for hour in hours}

                # Validamos que al menos los parámetros obligatorios de EDO 1 estén completos
                if all(
                    math.isfinite(value) and value != fill
                    for key in POWER_PARAMETERS
                    for value in series.get(key, {}).values()
                ):
                    return day, series, radiation_uses_mj(response)
        raise ValueError("Serie incompleta")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ParcelDataError("NASA POWER no devolvió las 24 horas requeridas para la simulación.") from exc


def radiation_uses_mj(response):
    units = response["parameters"]["ALLSKY_SFC_SW_DWN"]["units"].lower()
    units = units.replace(" ", "").replace("^", "").replace("²", "2")
    if units in {"w/m2", "wh/m2", "wh/m2/hour", "w-hr/m2", "w/m^2"}:
        return False
    if "mj" in units or units in {"mj/m2", "mj/m2/hr", "mj/m2/hour", "mj/hr"}:
        return True
    raise ValueError(f"Unidad de radiación desconocida: {units}")


def load_root_wetness(longitude, latitude, day):
    """Lee la humedad radicular diaria si el servicio la tiene disponible."""
    date_key = day.strftime("%Y%m%d")
    params = {
        "parameters": "GWETROOT", "community": "AG",
        "longitude": longitude, "latitude": latitude, "time-standard": "LST",
        "start": date_key, "end": date_key, "format": "JSON",
    }
    try:
        response = read_json(f"{POWER_DAILY_URL}?{urlencode(params)}")
        water = float(response["properties"]["parameter"]["GWETROOT"][date_key])
    except (OSError, KeyError, TypeError, ValueError):
        return None
    return water if 0 <= water <= 1 else None


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
    from backend.core.edo1_engine import compute_shield_state_and_color
    from backend.core.edo2_engine import compute_soil_limits, relative_stomatal_conductance, solve_edo2_step
    from backend.core.edo3_engine import SoilChemicalProperties, solve_edo3_step
    from backend.core.edo4_engine import execute_harvest_event, solve_edo4_step
    from backend.core.edo5_engine import solve_edo5_step, compute_soil_color, compute_soil_vitality_index
    from backend.core.physics import thermal_comfort_index
    from backend.models.crop_parameters import CROP_CATALOG, GLOBAL_CONSTANTS, get_crop_parameters
    from backend.services.simulation_service import SimulationService

    if not isinstance(payload, dict):
        raise ValueError("Envía la geometría de la parcela como JSON.")
    requested_crop = payload.get("crop_id", "papa")
    if not isinstance(requested_crop, str):
        raise ValueError("El identificador del cultivo debe ser texto.")
    crop_aliases = {"papa_canchan": "papa", "maiz_amilaceo": "maiz", "habas_verdes": "haba"}
    crop = crop_aliases.get(requested_crop, requested_crop)
    crop = crop if crop in CROP_CATALOG else "papa"
    crop_param = get_crop_parameters(crop)
    is_crop = crop_param.key != "suelo_desnudo_transicion"
    theta_fc = float(payload.get("theta_fc", 0.30))
    theta_wp = float(payload.get("theta_wp", 0.14))
    if not 0 <= theta_wp < theta_fc <= 1:
        raise ValueError("La humedad del suelo debe cumplir 0 ≤ θ de marchitez < θ de campo ≤ 1.")
    water_limits = compute_soil_limits(crop_param, theta_fc, theta_wp, float(payload.get("h_current_mm", payload.get("h0_mm", 400.0))))
    crop_param = replace(
        crop_param, W_fc=water_limits.w_cc, W_pmp=water_limits.w_pmp, W_crit=water_limits.w_crit,
    )
    h0_initial = float(payload.get("h0_mm", 400.0))
    h_start = float(payload.get("h_current_mm", h0_initial))
    if not math.isfinite(h0_initial) or h0_initial <= 0 or not 0 <= h_start <= h0_initial:
        raise ValueError("El espesor inicial debe ser positivo y el actual debe estar entre 0 y H(0).")
    water_input = payload.get("soil_water_mm")
    if water_input is not None:
        water = float(water_input)
        if not math.isfinite(water) or water < 0:
            raise ValueError("La humedad radicular debe ser un valor no negativo en mm.")
        soil_water_source = "manual"
    else:
        water = None
        soil_water_source = "auto_detect"

    cells, samples, reference = build_grid(payload.get("geometry"))
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    day, series, radiation_in_mj = load_power(*reference, yesterday)

    # Humedad radicular estimada al inicio del paso diario.
    if water is None:
        mean_gwet = load_root_wetness(*reference, day)
        if mean_gwet is not None:
            water = round(crop_param.W_pmp + mean_gwet * (crop_param.W_fc - crop_param.W_pmp), 2)
            soil_water_source = "NASA_POWER_GWETROOT"
        else:
            water = round(0.70 * crop_param.W_fc, 2)
            soil_water_source = "default_70pct_Wfc"
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
        is_radiation_mj_hr=radiation_in_mj, crop_parameters=crop_param,
    )
    for cell, thermal in zip(cells, result["cells"]):
        thermal.update(cell)
    area = sum(cell["area_m2"] for cell in cells)
    result["lot_mean_temp"] = round(sum(c["area_m2"] * c["mean_canopy_temp"] for c in result["cells"]) / area, 2)

    # Resolución acoplada de EDO 2 (Balance Hidrológico Radicular) y EDO 3 (Macronutrientes NPK) por celda con SRTM
    rh_mean = sum(series["RH2M"].values()) / float(len(series["RH2M"]))
    rainfall = series.get("PRECTOT") or series.get("PRECTOTCORR", {})
    has_rainfall = all(math.isfinite(rainfall.get(ts, -1)) and rainfall.get(ts, -1) >= 0
                       for ts in result["timestamps"])
    precip_total = sum(rainfall[ts] for ts in result["timestamps"]) if has_rainfall else 0.0
    radiation = sum(series["ALLSKY_SFC_SW_DWN"].values())
    rad_daily_mj = radiation if radiation_in_mj else radiation * 0.0036
    soil_props = SoilChemicalProperties(
        om_pct=float(payload.get("soil_om_pct", 3.0)),
        cic_cmolc_kg=float(payload.get("soil_cic", 22.0)),
        ph=float(payload.get("soil_ph", 6.8)),
        ec_ds_m=float(payload.get("soil_ec", 0.8))
    )
    init_npk = payload.get("nutrientes_iniciales", {})
    init_n = float(init_npk.get("N", 85.0))
    init_p = float(init_npk.get("P", 32.0))
    init_k = float(init_npk.get("K", 180.0))
    b_est = crop_param.B_max_t_ha * 0.45 if is_crop else 0.0

    last_edo3_step = None
    for thermal in result["cells"]:
        slope = thermal.get("slope_deg", 0.0)
        edo2_step = solve_edo2_step(
            w_current_mm=water,
            precip_mm=precip_total,
            t_air_c=sum(thermal["hourly_air_temps"]) / len(thermal["hourly_air_temps"]),
            rh_pct=rh_mean,
            slope_deg=slope,
            crop=crop_param,
            theta_fc=theta_fc,
            theta_wp=theta_wp,
            is_crop=is_crop,
            biomass_t_ha=b_est,
            depth_mm=h_start, canopy_temp_c=thermal["mean_canopy_temp"],
            dt_days=1.0
        )

        # EDO 5 usa la cobertura al inicio del paso diario.
        edo5_step = solve_edo5_step(
            h_current_mm=h_start,
            precip_mm=precip_total,
            slope_deg=slope,
            biomass_t_ha=b_est,
            is_transition=not is_crop,
            h_initial_mm=h0_initial,
            theta_fc=theta_fc,
            theta_wp=theta_wp,
            current_nutrients_kg_ha={"N": init_n, "P": init_p, "K": init_k}
        )
        eros_rate = abs(edo5_step.dh_dt_mm_day)

        # Resolución acoplada de EDO 3 por celda
        cell_t = thermal["mean_canopy_temp"]
        edo3_step = solve_edo3_step(
            n_current_kg_ha=init_n,
            p_current_kg_ha=init_p,
            k_current_kg_ha=init_k,
            w_mm=edo2_step.soil_water_mm,
            w_cc_mm=crop_param.W_fc,
            t_soil_c=cell_t,
            crop=crop_param,
            soil=soil_props,
            biomass_t_ha=b_est,
            erosion_rate_mm_day=eros_rate,
            is_crop=is_crop
        )
        last_edo3_step = edo3_step

        # Resolución acoplada de EDO 4 (Biomasa B y Teledetección NDVI con radiación NASA POWER)
        edo4_step = solve_edo4_step(
            b_current_t_ha=b_est,
            f_rad_daily_mj_m2=rad_daily_mj,
            temp_canopy_c=cell_t,
            soil_water_mm=edo2_step.soil_water_mm,
            nitrogen_kg_ha=edo3_step.n_kg_ha,
            phosphorus_kg_ha=edo3_step.p_kg_ha,
            potassium_kg_ha=edo3_step.k_kg_ha,
            crop=crop_param,
            q_is_crop=is_crop,
            dt_days=1.0
        )
        harvest_edo4 = execute_harvest_event(
            biomass_pre_harvest_t_ha=edo4_step.biomass_t_ha,
            crop=crop_param
        )

        # Se combina T horaria con W, NPK y el Área de Lissajous A_L resultantes del paso.
        eta_water = relative_stomatal_conductance(edo2_step.soil_water_mm, water_limits) if is_crop else 0.0
        span_w_soil = max(1e-4, water_limits.w_cc - water_limits.w_pmp)
        soil_water_sat = max(0.0, min(1.0, (edo2_step.soil_water_mm - water_limits.w_pmp) / span_w_soil)) if water_limits.w_cc > 0 else 0.0
        thermal_comfort = [
            thermal_comfort_index(t, crop_param.T_opt, crop_param.delta_T_tol)
            for t in thermal["hourly_canopy_temps"]
        ]
        hourly_psi_raw = [value * eta_water * edo3_step.eta_nutrientes for value in thermal_comfort]
        mean_psi_raw = sum(hourly_psi_raw) / max(1, len(hourly_psi_raw))
        shield_eval = compute_shield_state_and_color(
            lissajous_area=thermal.get("lissajous_area", 0.0) * eta_water,
            psi_environmental=mean_psi_raw,
            is_crop=is_crop,
        )
        omega_l = float(GLOBAL_CONSTANTS.get("peso_lissajous_escudo_omega_L", 0.55))
        eta_l = shield_eval["eta_lissajous"]

        # Color del terreno entre Marrón (101,67,33) y Gris (128,128,128) según nutrientes, humedad y H
        coupled_soil_color = compute_soil_color(
            retention_ratio=edo5_step.soil_retention_ratio,
            eta_nutrientes=edo3_step.eta_nutrientes,
            water_saturation=soil_water_sat,
        )
        coupled_soil_vitality = compute_soil_vitality_index(
            retention_ratio=edo5_step.soil_retention_ratio,
            eta_nutrientes=edo3_step.eta_nutrientes,
            water_saturation=soil_water_sat,
        )

        thermal.update(
            shield_enabled=is_crop,
            rain_exposure_alert=not is_crop,
            eta_lissajous=eta_l if is_crop else 0.0,
            shield_score=shield_eval["shield_score"] if is_crop else 0.0,
            shield_state=shield_eval["shield_state"],
            shield_color_rgb=shield_eval["shield_color_rgb"],
            hourly_thermal_comfort=[round(value, 4) for value in thermal_comfort] if is_crop else None,
            water_condition_index=round(eta_water, 4) if is_crop else None,
            hourly_environmental_index=[
                round(omega_l * eta_l + (1.0 - omega_l) * psi_h, 4) for psi_h in hourly_psi_raw
            ] if is_crop else None,
            soil_water_mm=edo2_step.soil_water_mm,
            etc_mm=edo2_step.etc_mm,
            drainage_mm=edo2_step.drainage_mm,
            gamma_c_relative=edo2_step.gamma_c_relative,
            is_irrigation_needed=is_crop and edo2_step.is_irrigation_needed,
            suggested_irrigation_mm=edo2_step.suggested_irrigation_mm if is_crop else 0.0,
            nutrientes_n_kg_ha=edo3_step.n_kg_ha,
            nutrientes_p_kg_ha=edo3_step.p_kg_ha,
            nutrientes_k_kg_ha=edo3_step.k_kg_ha,
            eta_nutrientes=edo3_step.eta_nutrientes,
            limiting_nutrient=edo3_step.limiting_nutrient,
            biological_n_fixation_kg=edo3_step.biological_n_fixation_kg,
            biomass_t_ha=edo4_step.biomass_t_ha,
            db_dt_t_ha_day=edo4_step.db_dt,
            ndvi_satelital=edo4_step.simulated_ndvi,
            canopy_cover_pct=round(edo4_step.canopy_cover_fraction * 100, 1),
            yield_commercial_t_ha=harvest_edo4.commercial_yield_t_ha,
            net_margin_usd_ha=harvest_edo4.net_margin_usd_ha,
            h_current_mm=edo5_step.h_current_mm,
            h_initial_mm=edo5_step.h_initial_mm,
            erosion_loss_mm=edo5_step.erosion_loss_step_mm,
            accumulated_erosion_mm=edo5_step.accumulated_erosion_mm,
            rain_height_variation_mm=edo5_step.rain_height_variation_mm,
            visual_height_delta_m=edo5_step.visual_height_delta_m,
            dh_dt_mm_day=edo5_step.dh_dt_mm_day,
            soil_retention_ratio=edo5_step.soil_retention_ratio,
            soil_vitality_index=coupled_soil_vitality,
            soil_color_rgb=coupled_soil_color,
            p_drag_kg_ha=edo5_step.nutrient_drag_kg_ha.get("P", 0.0)
        )

    mean_water = round(sum(c["area_m2"] * c["soil_water_mm"] for c in result["cells"]) / area, 2)
    mean_etc = round(sum(c["area_m2"] * c["etc_mm"] for c in result["cells"]) / area, 2)
    mean_drainage = round(sum(c["area_m2"] * c["drainage_mm"] for c in result["cells"]) / area, 2)
    any_irrigation = any(c["is_irrigation_needed"] for c in result["cells"])
    max_suggested_irr = max(c["suggested_irrigation_mm"] for c in result["cells"])

    mean_n = round(sum(c["area_m2"] * c["nutrientes_n_kg_ha"] for c in result["cells"]) / area, 2)
    mean_p = round(sum(c["area_m2"] * c["nutrientes_p_kg_ha"] for c in result["cells"]) / area, 2)
    mean_k = round(sum(c["area_m2"] * c["nutrientes_k_kg_ha"] for c in result["cells"]) / area, 2)
    mean_eta_nut = round(sum(c["area_m2"] * c["eta_nutrientes"] for c in result["cells"]) / area, 3)

    mean_erosion = round(sum(c["area_m2"] * c["erosion_loss_mm"] for c in result["cells"]) / area, 5)
    mean_h = round(sum(c["area_m2"] * c["h_current_mm"] for c in result["cells"]) / area, 2)
    mean_p_drag = round(sum(c["area_m2"] * c["p_drag_kg_ha"] for c in result["cells"]) / area, 5)
    mean_b = round(sum(c["area_m2"] * c["biomass_t_ha"] for c in result["cells"]) / area, 2)
    mean_ndvi = round(sum(c["area_m2"] * c["ndvi_satelital"] for c in result["cells"]) / area, 3)
    mean_yield = round(sum(c["area_m2"] * c["yield_commercial_t_ha"] for c in result["cells"]) / area, 2)
    hotspot_cell = max(result["cells"], key=lambda c: c.get("erosion_loss_mm", 0.0)) if result["cells"] else {}

    if mean_erosion < 0.005:
        erosion_risk = "Bajo"
    elif mean_erosion < 0.03:
        erosion_risk = "Moderado"
    elif mean_erosion < 0.10:
        erosion_risk = "Severo"
    else:
        erosion_risk = "Crítico"

    if mean_water >= crop_param.W_crit:
        water_status = "Confort Hídrico"
    elif mean_water > crop_param.W_pmp:
        water_status = "Estrés Hídrico"
    else:
        water_status = "Punto de Marchitez"

    result.update(
        lot_mean_soil_water_mm=mean_water,
        lot_mean_etc_mm=mean_etc,
        lot_mean_drainage_mm=mean_drainage,
        water_status=water_status,
        irrigation_alert=any_irrigation,
        suggested_irrigation_mm=max_suggested_irr,
        soil_moisture_source=soil_water_source,
        precipitation_daily_mm=round(precip_total, 2) if has_rainfall else None,
        lot_mean_n_kg_ha=mean_n,
        lot_mean_p_kg_ha=mean_p,
        lot_mean_k_kg_ha=mean_k,
        lot_mean_eta_nutrientes=mean_eta_nut,
        limiting_nutrient=last_edo3_step.limiting_nutrient if last_edo3_step else "N",
        biological_n_fixation_kg=round(sum(c["area_m2"] * c["biological_n_fixation_kg"] for c in result["cells"]) / area, 2),
        lot_mean_biomass_t_ha=mean_b,
        lot_mean_ndvi=mean_ndvi,
        lot_mean_yield_t_ha=mean_yield,
        lot_mean_erosion_loss_mm=mean_erosion,
        lot_mean_h_mm=mean_h,
        lot_mean_p_drag_kg_ha=mean_p_drag,
        erosion_risk_level=erosion_risk,
        erosion_hotspot_cell=hotspot_cell.get("cell_id"),
        erosion_hotspot_loss_mm=hotspot_cell.get("erosion_loss_mm"),
        erosion_hotspot_slope_deg=round(hotspot_cell.get("slope_deg", 0.0), 1) if hotspot_cell else 0.0,
        data_sources={
            "meteorology": "NASA POWER (T2M, ALLSKY_SFC_SW_DWN, RH2M)",
            "precipitation": "NASA POWER" if has_rainfall else None,
            "soil_moisture": soil_water_source,
            "topography": "SRTM v3 30m (Open Topo Data / USGS)",
            "biomass_ndvi": "NDVI derivado de biomasa simulada (sin observación orbital)",
            "soil_attributes": "Parámetros ingresados o valores de referencia"
        }
    )
    result.update(
        date=day.isoformat(),
        time_standard="LST",
        cell_size_m=CELL_M,
        climate_source="NASA POWER",
        terrain_source="SRTM v3 (Open Topo Data)",
        crop_id=crop,
        phase="cultivo" if is_crop else "transicion",
        optimal_canopy_temp=crop_param.T_opt if is_crop else None,
        reference_crop_used=crop == "papa" and requested_crop not in ("papa", "papa_canchan"),
    )
    log_parcel_telemetry(day, reference, series, elevations[-1], result)
    return result
