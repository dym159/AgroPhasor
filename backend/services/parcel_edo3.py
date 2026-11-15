"""
Servicio de Simulación de Parcela para EDO 3 (Dinámica Vectorial de Macronutrientes).
Conecta el forzamiento agroclimático, parámetros de suelo (SSURGO/WSS) y secuencias de cultivo
con el motor agrofísico `edo3_engine`.
"""

from typing import Dict, Any, List, Optional, Tuple

from backend.models.crop_parameters import get_crop_parameters, CROP_CATALOG, CropParameters
from backend.models.edo3_validator import validate_edo3_catalog
from backend.core.edo3_engine import (
    solve_edo3_step,
    simulate_edo3_timeseries,
    calculate_phi_ph_ec,
    compute_liebig_factor,
    SoilChemicalProperties,
    EDO3StepOutput
)


class ParcelEDO3Service:
    """Servicio agrofísico para la ejecución de simulaciones de EDO 3 a nivel de parcela."""

    @staticmethod
    def validate_catalog(catalog_path_or_dict: Any) -> Dict[str, Any]:
        """Valida formalmente un archivo o diccionario JSON para EDO 3."""
        return validate_edo3_catalog(catalog_path_or_dict)

    @staticmethod
    def simulate_timeseries(
        w_series: List[float],
        t_soil_series: List[float],
        crop_id: str = "maiz",
        om_pct: float = 3.0,
        cic_cmolc_kg: float = 22.0,
        ph: float = 6.8,
        ec_ds_m: float = 0.8,
        w_cc_mm: float = 120.0,
        n0_kg_ha: float = 85.0,
        p0_kg_ha: float = 32.0,
        k0_kg_ha: float = 180.0,
        erosion_rate_series: Optional[List[float]] = None,
        is_crop: bool = True,
        dt_days: float = 1.0,
        custom_catalog_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta la simulación temporal de EDO 3 para un cultivo y perfil de suelo dados.
        """
        crop = get_crop_parameters(crop_id)

        if custom_catalog_path:
            validation = validate_edo3_catalog(custom_catalog_path)
            if not validation["valid"]:
                raise ValueError(f"Catálogo customizado inválido para EDO 3: {validation['errors']}")

        phi_chem = calculate_phi_ph_ec(ph, ec_ds_m)
        soil = SoilChemicalProperties(
            om_pct=om_pct,
            cic_cmolc_kg=cic_cmolc_kg,
            ph=ph,
            ec_ds_m=ec_ds_m,
            phi_ph_ec=phi_chem
        )

        return simulate_edo3_timeseries(
            w_series=w_series,
            t_soil_series=t_soil_series,
            crop=crop,
            soil=soil,
            w_cc_mm=w_cc_mm,
            n0_kg_ha=n0_kg_ha,
            p0_kg_ha=p0_kg_ha,
            k0_kg_ha=k0_kg_ha,
            erosion_rate_series=erosion_rate_series,
            is_crop=is_crop,
            dt_days=dt_days
        )

    @staticmethod
    def simulate_rotation(
        stages: List[Dict[str, Any]],
        t_soil_series: List[float],
        w_series: List[float],
        om_pct: float = 3.0,
        cic_cmolc_kg: float = 22.0,
        ph: float = 6.8,
        ec_ds_m: float = 0.8,
        w_cc_mm: float = 120.0,
        n0_kg_ha: float = 85.0,
        p0_kg_ha: float = 32.0,
        k0_kg_ha: float = 180.0,
        dt_days: float = 1.0
    ) -> Dict[str, Any]:
        """
        Simula una secuencia de rotación multietapa (ej: Maíz -> Barbecho/Rastrojo -> Leguminosa).
        Cada etapa en `stages` contiene:
        - 'crop_id': str
        - 'duration_days': int
        - 'is_crop': bool
        """
        phi_chem = calculate_phi_ph_ec(ph, ec_ds_m)
        soil = SoilChemicalProperties(
            om_pct=om_pct,
            cic_cmolc_kg=cic_cmolc_kg,
            ph=ph,
            ec_ds_m=ec_ds_m,
            phi_ph_ec=phi_chem
        )

        curr_n, curr_p, curr_k = n0_kg_ha, p0_kg_ha, k0_kg_ha
        global_n, global_p, global_k = [curr_n], [curr_p], [curr_k]
        global_eta = []
        global_limiting = []
        time_offset = 0

        stage_summaries = []

        for stg_idx, stage in enumerate(stages):
            cid = stage.get("crop_id", "maiz")
            crop = get_crop_parameters(cid)
            days = int(stage.get("duration_days", 60))
            is_c = bool(stage.get("is_crop", True))

            stg_w = w_series[time_offset:time_offset + days]
            stg_t = t_soil_series[time_offset:time_offset + days]

            # Si faltan días en la serie meteorológica, replicar el último valor
            if len(stg_w) < days:
                last_w = stg_w[-1] if stg_w else 80.0
                stg_w = stg_w + [last_w] * (days - len(stg_w))
            if len(stg_t) < days:
                last_t = stg_t[-1] if stg_t else 18.0
                stg_t = stg_t + [last_t] * (days - len(stg_t))

            stg_res = simulate_edo3_timeseries(
                w_series=stg_w,
                t_soil_series=stg_t,
                crop=crop,
                soil=soil,
                w_cc_mm=w_cc_mm,
                n0_kg_ha=curr_n,
                p0_kg_ha=curr_p,
                k0_kg_ha=curr_k,
                is_crop=is_c,
                dt_days=dt_days
            )

            curr_n = stg_res["summary"]["final_NPK"][0]
            curr_p = stg_res["summary"]["final_NPK"][1]
            curr_k = stg_res["summary"]["final_NPK"][2]

            global_n.extend(stg_res["n_series_kg_ha"][1:])
            global_p.extend(stg_res["p_series_kg_ha"][1:])
            global_k.extend(stg_res["k_series_kg_ha"][1:])
            global_eta.extend(stg_res["eta_liebig_series"])
            global_limiting.extend(stg_res["limiting_nutrient_series"])

            stage_summaries.append({
                "stage_index": stg_idx + 1,
                "crop": crop.name,
                "duration_days": days,
                "is_crop": is_c,
                "initial_NPK": stg_res["summary"]["initial_NPK"],
                "final_NPK": stg_res["summary"]["final_NPK"],
                "n_fixed_kg_ha": stg_res["summary"]["total_biological_n_fixed_kg_ha"],
                "k_recycled_kg_ha": stg_res["summary"]["total_k_stover_recycled_kg_ha"],
                "mean_eta_liebig": stg_res["summary"]["mean_eta_liebig"]
            })

            time_offset += days

        return {
            "stages": stage_summaries,
            "overall_summary": {
                "initial_NPK": [n0_kg_ha, p0_kg_ha, k0_kg_ha],
                "final_NPK": [curr_n, curr_p, curr_k],
                "delta_N": round(curr_n - n0_kg_ha, 2),
                "delta_P": round(curr_p - p0_kg_ha, 2),
                "delta_K": round(curr_k - k0_kg_ha, 2),
                "mean_eta_liebig": round(float(sum(global_eta) / max(1, len(global_eta))), 3),
                "final_eta_liebig": global_eta[-1] if global_eta else 0.0
            },
            "trajectories": {
                "n_series": global_n,
                "p_series": global_p,
                "k_series": global_k,
                "eta_series": global_eta,
                "limiting_nutrient_series": global_limiting
            }
        }
