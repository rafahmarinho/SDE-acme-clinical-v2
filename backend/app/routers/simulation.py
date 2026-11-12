"""API router: simulation control (scenarios, advance, reset). Administrators only.

Critical actions (T342): changing the scenario and resetting demo data require explicit
confirmation fields in the request body (the API rejects them with 422 otherwise, so the UI
warning cannot be skipped), and responses repeat the consequence of the action. Every action is
audited. Advance is retried a bounded number of times on deadlock/lock timeout (T633).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.core.audit import record_event
from app.core.ratelimit import enforce_shared_limit
from app.core.security import CurrentPrincipal, Perm, Principal, require, require_recent_auth
from app.db import fetch_one, transaction
from app.schemas import Out, SimulationAdvanceIn, SimulationOut, SimulationResetIn, SimulationScenarioIn
from app.services import alarms, resilience, simulation

router = APIRouter(prefix="/v1/simulation", tags=["simulation"])
Operator = Annotated[Principal, Depends(require(Perm.SIMULATION_CONTROL))]
# Reset destroys demo data: step-up re-authentication (recent password/MFA) is required.
ResetOperator = Annotated[Principal, Depends(require_recent_auth(Perm.SIMULATION_CONTROL))]

SCENARIO_WARNING = ("Scenario changes alter the simulated readings of every affected monitor and will raise or clear "
                    "alarms on the next tick. This action is recorded in the audit log with your name and time.")
RESET_WARNING = ("All readings, alarms and observations were deleted and monitors returned to baseline. "
                 "The audit trail was preserved. This action is recorded in the audit log.")


class ScenarioChangeIn(SimulationScenarioIn):
    acknowledged: Literal[True] = Field(description="Must be true: the operator read the scenario-change warning.")


class SimulationResetConfirmedIn(SimulationResetIn):
    acknowledged: Literal[True] = Field(description="Must be true: the operator read the reset warning.")


class SimulationActionOut(SimulationOut):
    notice: str


class AdvanceOut(Out):
    tick: int
    version: int
    readings: int
    raised: int
    resolved: int
    evaluation_errors: int
    watchdog_connection_lost: int


async def _state(conn) -> dict:
    row = await fetch_one(conn, "select scenario::text as scenario, tick, version, updated_at from public.simulation_state where id = 1")
    return dict(row)


@router.get("", response_model=SimulationOut)
async def get_state(principal: CurrentPrincipal) -> SimulationOut:
    async with transaction(principal, read_only=True) as conn:
        return SimulationOut(**await _state(conn))


@router.post("/scenario", response_model=SimulationActionOut)
async def set_scenario(body: ScenarioChangeIn, request: Request, principal: Operator) -> SimulationActionOut:
    async with transaction(principal) as conn:
        await enforce_shared_limit(conn, "simulation", fetch_one)
        await simulation.set_scenario(conn, str(principal.user_id), body.scenario.value, [str(m) for m in body.monitor_ids])
        await record_event(principal, "simulation.scenario_set", "simulation", "1",
                           details={"scenario": body.scenario.value, "monitors": len(body.monitor_ids), "acknowledged": True},
                           conn=conn, request_id=request.state.request_id)
        return SimulationActionOut(**await _state(conn), notice=SCENARIO_WARNING)


@router.post("/advance", response_model=AdvanceOut)
async def advance(body: SimulationAdvanceIn, request: Request, principal: Operator) -> AdvanceOut:
    async def run() -> dict:
        async with transaction(principal) as conn:
            await enforce_shared_limit(conn, "simulation", fetch_one)
            result = await simulation.advance(conn, str(principal.user_id), body.steps, body.expected_version)
            lost = await alarms.watchdog_sweep(conn)
            result["watchdog_connection_lost"] = len(lost)
            await record_event(principal, "simulation.advanced", "simulation", "1", details=result, conn=conn,
                               request_id=request.state.request_id)
        return result

    return AdvanceOut(**await resilience.with_retry(run))


@router.post("/reset", response_model=SimulationActionOut)
async def reset(body: SimulationResetConfirmedIn, request: Request, principal: ResetOperator) -> SimulationActionOut:
    async with transaction(principal) as conn:
        await enforce_shared_limit(conn, "simulation-reset", fetch_one)
        await simulation.reset(conn, str(principal.user_id))
        await record_event(principal, "simulation.reset", "simulation", "1", details={"acknowledged": True}, conn=conn,
                           request_id=request.state.request_id)
        return SimulationActionOut(**await _state(conn), notice=RESET_WARNING)
