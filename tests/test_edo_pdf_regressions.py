"""Casos sintéticos de balance; no representan observaciones de campo."""
import pytest
import math
from dataclasses import replace
from backend.core.edo2_engine import solve_edo2_step
from backend.models.crop_parameters import CROP_CATALOG
from backend.core.edo1_engine import solve_edo1_step
from backend.core.edo3_engine import solve_edo3_step
from backend.core.edo4_engine import solve_edo4_step
from backend.core.edo5_engine import solve_edo5_step
from backend.core.physics import actual_vapor_pressure, saturation_vapor_pressure
from backend.services.coupled_model import advance_day


@pytest.mark.parametrize("precip", [0., 1.])
def test_water_balance_when_linear_reservoir_empties(precip):
    """Sin evaporación/drenaje, ET no excede W inicial + infiltración."""
    result = solve_edo2_step(100,precip,30,0,0,CROP_CATALOG['papa'],
                            depth_mm=400,e_suelo0=0,kd=0,dt_days=20)
    assert result.soil_water_mm == 0
    balance = 100+result.infiltration_mm-result.etc_mm-result.drainage_mm-result.runoff_mm
    assert result.soil_water_mm == pytest.approx(balance,abs=.012)


def test_thermal_matches_frozen_latent_pdf():
    crop=CROP_CATALOG['papa']
    water=crop.W_crit+1
    latent=crop.lambda_gamma_max*max(0,saturation_vapor_pressure(24)-actual_vapor_pressure(20,60))
    equilibrium=20+(crop.alpha*400-latent)/crop.hc
    expected=equilibrium+(24-equilibrium)*math.exp(-crop.hc*3600/crop.Cp)
    assert solve_edo1_step(24,20,400,60,water,crop).t_canopy_c == pytest.approx(expected)


def test_nutrient_diagnostic_integrates_state_with_sources():
    r=solve_edo3_step(100,0,0,100,120,20,CROP_CATALOG['papa'],is_crop=False,
                      biomass_t_ha=0,k_min0=0,k_ln=.035,k_lk=0,fertilizer_npk_kg_ha=(2,0,0))
    assert r.n_kg_ha == pytest.approx(100+2-r.leaching_n_kg,abs=1e-10)


def test_complete_npk_balances_and_fractional_step():
    initial=dict(N=100.,P=40.,K=120.)
    r=solve_edo3_step(*initial.values(),100,120,20,CROP_CATALOG['frijol'],
                      biomass_t_ha=2,erosion_rate_mm_day=.2,dt_days=.25)
    leached=dict(N=r.leaching_n_kg,P=0.,K=r.leaching_k_kg)
    for key,value in zip(initial,(r.n_kg_ha,r.p_kg_ha,r.k_kg_ha)):
        balance=initial[key]+r.sources_npk_kg_ha[key]-r.uptake_npk_kg_ha[key]-r.erosion_npk_kg_ha[key]-leached[key]
        assert value == pytest.approx(balance,abs=1e-10)


@pytest.mark.parametrize('temperature',[10,20,30])
def test_residue_constant_decay_preserves_inherited_mass(temperature):
    crop=CROP_CATALOG['papa']; initial=2*crop.B_max_t_ha
    r=solve_edo4_step(initial,0,temperature,100,100,40,120,crop,q_is_crop=False,k_dec_daily=.025)
    assert r.biomass_t_ha == pytest.approx(initial*math.exp(-.025),abs=1e-12)


def test_zero_maintenance_and_growth_and_biomass_balance():
    crop=replace(CROP_CATALOG['papa'],km_c=0)
    r=solve_edo4_step(1,0,20,100,100,40,120,crop)
    assert r.biomass_t_ha == 1
    r=solve_edo4_step(1,18,20,100,100,40,120,CROP_CATALOG['papa'])
    assert r.biomass_t_ha == pytest.approx(1+r.gross_growth_t_ha-r.maintenance_loss_t_ha,abs=1e-12)


def test_effective_erosion_rate_when_horizon_exhausts():
    r=solve_edo5_step(.001,100,60,0,is_transition=True,dt_days=2)
    assert r.dh_dt_mm_day == pytest.approx(-r.erosion_loss_step_mm/2)


def test_coupling_temperature_memory_water_balance_and_convergence():
    crop=CROP_CATALOG['papa']; weather=(3.,16.,65.,18.)
    initial=(100.,(100.,40.,120.),400.,.2,())
    state,diag=advance_day(initial,crop,weather,30)
    assert isinstance(state[4][-1],tuple)
    assert state[4][-1][1] == diag['canopy']
    balance=100+diag['water_infiltration_mm']-diag['water_etc_mm']-diag['water_drainage_mm']-diag['water_runoff_mm']
    assert state[0] == pytest.approx(balance,abs=1e-10)
    # Refinamiento con forzantes sintéticas constantes; referencia dt=1/128 día.
    def evolve(parts):
        current=initial
        for _ in range(parts):
            current,_=advance_day(current,crop,weather,10,dt_days=1/parts)
        return (current[0]/100,*[v/100 for v in current[1]],current[2]/400,current[3])
    reference=evolve(128)
    errors=[sum(abs(a-b) for a,b in zip(evolve(n),reference)) for n in (1,2,4)]
    assert errors[2] < errors[1] < errors[0]
