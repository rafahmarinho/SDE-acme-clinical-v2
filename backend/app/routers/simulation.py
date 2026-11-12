"""API router: simulation control (scenarios, advance, reset). Administrators only."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.audit import record_event
from app.core.security import CurrentPrincipal, Perm, Principal, require
from app.db import fetch_one, transaction
from app.schemas import SimulationAdvanceIn, SimulationOut, SimulationResetIn, SimulationScenarioIn
from app.services import simulation

router = APIRouter(prefix="/v1/simulation", tags=["simulation"])
Operator = Annotated[Principal, Depends(require(Perm.SIMULATION_CONTROL))]


async def _state(conn) -> SimulationOut:
    row = await fetch_one(conn, "select scenario::text as scenario, tick, version, updated_at from public.simulation_state where id = 1")
    return SimulationOut(**row)


@router.get("", response_model=SimulationOut)
async def get_state(principal: CurrentPrincipal) -> SimulationOut:
    async with transaction(principal) as conn:
        return await _state(conn)


@router.post("/scenario", response_model=SimulationOut)
async def set_scenario(body: SimulationScenarioIn, request: Request, principal: Operator) -> SimulationOut:
    async with transaction(principal) as conn:
        await simulation.set_scenario(conn, str(principal.user_id), body.scenario.value, [str(m) for m in body.monitor_ids])
        await record_event(principal, "simulation.scenario_set", "simulation", "1",
                           details={"scenario": body.scenario.value, "monitors": len(body.monitor_ids)}, conn=conn,
                           request_id=request.state.request_id)
        return await _state(conn)


@router.post("/advance")
async def advance(body: SimulationAdvanceIn, request: Request, principal: Operator) -> dict:
    async with transaction(principal) as conn:
        result = await simulation.advance(conn, str(principal.user_id), body.steps, body.expected_version)
        await record_event(principal, "simulation.advanced", "simulation", "1", details=result, conn=conn,
                           request_id=request.state.request_id)
    return result


@router.post("/reset", response_model=SimulationOut)
async def reset(body: SimulationResetIn, request: Request, principal: Operator) -> SimulationOut:
    async with transaction(principal) as conn:
        await simulation.reset(conn, str(principal.user_id))
        await record_event(principal, "simulation.reset", "simulation", "1", conn=conn, request_id=request.state.request_id)
        return await _state(conn)
