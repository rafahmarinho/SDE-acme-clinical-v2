"""Pydantic request/response schemas with strict types and field constraints.

* Request models (`Strict`) forbid unknown fields (`extra="forbid"`, i.e. `additionalProperties: false`
  in the OpenAPI contract), so clients cannot smuggle read-only attributes such as `role`,
  `author_id` or `acknowledged_by`; server-owned values come from the verified session (T33, T569).
* Every request field is typed and bounded: strings have a max length and a character policy,
  numbers are strict (no "40"/40.0/true coercion) with min/max, lists have max items, choices are
  enums (T31, T34, T537, T569).
* Free text is NFC-normalised and refuses NUL/control/bidi/zero-width characters; names are
  single-script letter allow-lists (anti-homoglyph); staff e-mails are ASCII (T34, T127, T1038).
* Response models list exactly the fields the UI needs (no secrets, hashes or internal columns),
  and every collection is returned inside the `Page` object envelope, never as a top-level JSON
  array (T167, T2140).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StrictBool, model_validator

from app.core.validation import ascii_email, clean_text, person_name, single_line

CleanText = Annotated[str, AfterValidator(clean_text)]
ShortText = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(single_line)]
SearchText = Annotated[str, Field(max_length=60), AfterValidator(single_line)]
PersonName = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(person_name)]
StaffEmail = Annotated[EmailStr, Field(max_length=254), AfterValidator(ascii_email)]

# Largest page any list endpoint may return (result-set size bound, T2609).
MAX_PAGE_SIZE = 100
MAX_OFFSET = 10_000


def bounded_int(ge: int, le: int):
    """Strict integer (JSON numbers only: no strings, floats or booleans) within [ge, le]."""
    return Annotated[int, Field(strict=True, ge=ge, le=le)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=4000)


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(Out, Generic[T]):
    """Collection envelope: always a JSON object (anti JSON-hijacking) with a bounded `items` list."""

    items: list[T]
    next_offset: int | None = None


class RoleName(StrEnum):
    nurse = "nurse"
    physician = "physician"
    biomed_tech = "biomed_tech"
    admin = "admin"


class VitalParameter(StrEnum):
    heart_rate = "heart_rate"
    spo2 = "spo2"
    resp_rate = "resp_rate"
    bp_systolic = "bp_systolic"
    bp_diastolic = "bp_diastolic"


class Scenario(StrEnum):
    normal = "normal"
    low_saturation = "low_saturation"
    low_battery = "low_battery"
    sensor_fault = "sensor_fault"
    connection_loss = "connection_loss"


# Clinically plausible bounds for configurable alarm limits (server-side, regardless of UI).
THRESHOLD_BOUNDS: dict[VitalParameter, tuple[int, int]] = {
    VitalParameter.heart_rate: (20, 250),
    VitalParameter.spo2: (70, 100),
    VitalParameter.resp_rate: (4, 60),
    VitalParameter.bp_systolic: (50, 250),
    VitalParameter.bp_diastolic: (30, 150),
}


# ---------- identity / profile ----------
class Me(Out):
    user_id: UUID
    email: str
    full_name: str
    role: RoleName
    ward_ids: list[UUID]
    permissions: list[str]
    previous_login_at: datetime | None
    privacy_notice_accepted_at: datetime | None
    session_idle_minutes: int


class ProfileUpdate(Strict):
    full_name: PersonName


class ProfileExport(Out):
    profile: dict
    ward_ids: list[UUID]
    observations_authored: int
    events: list[dict]
    exported_at: datetime


# ---------- wards / patients ----------
class WardOut(Out):
    id: UUID
    code: str
    name: str
    bed_count: int
    patient_count: int
    active_alarms: int


class BedOut(Out):
    id: UUID
    ward_id: UUID
    label: str
    patient_id: UUID | None
    patient_pseudonym: str | None
    monitor_id: UUID | None
    monitor_serial: str | None
    occupied: bool


class PatientOut(Out):
    id: UUID
    pseudonym: str
    display_name: str
    birth_year: int | None
    ward_id: UUID
    bed_label: str | None
    monitor_serial: str | None
    active_alarms: int
    admitted_at: datetime


class ReadingOut(Out):
    recorded_at: datetime
    heart_rate: int | None
    spo2: int | None
    resp_rate: int | None
    bp_systolic: int | None
    bp_diastolic: int | None
    ecg: list[float] | None
    quality: str


class ObservationIn(Strict):
    body: Annotated[CleanText, Field(min_length=1, max_length=2000)]


class ObservationOut(Out):
    id: UUID
    author_name: str
    body: str
    created_at: datetime


# ---------- alarms / thresholds ----------
class AlarmOut(Out):
    id: UUID
    patient_id: UUID | None
    patient_pseudonym: str | None
    monitor_serial: str
    type: str
    priority: str
    state: str
    message: str
    raised_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by_name: str | None


class AlarmAck(Strict):
    note: Annotated[CleanText, Field(max_length=500)] | None = None


class ThresholdOut(Out):
    id: UUID
    ward_id: UUID | None
    patient_id: UUID | None
    parameter: VitalParameter
    low_limit: int
    high_limit: int
    updated_at: datetime


class ThresholdUpdate(Strict):
    parameter: VitalParameter
    low_limit: bounded_int(0, 300)
    high_limit: bounded_int(0, 300)
    confirm: StrictBool = Field(description="Must be true: the user confirmed the change to a clinical alarm limit.")

    @model_validator(mode="after")
    def _plausible(self) -> ThresholdUpdate:
        lo, hi = THRESHOLD_BOUNDS[self.parameter]
        if not (lo <= self.low_limit < self.high_limit <= hi):
            raise ValueError(f"limits for {self.parameter.value} must satisfy {lo} <= low < high <= {hi}")
        if not self.confirm:
            raise ValueError("changing an alarm limit requires explicit confirmation")
        return self


# ---------- devices ----------
class MonitorOut(Out):
    id: UUID
    serial: str
    model: str
    firmware_version: str
    status: str
    battery_pct: int
    last_heartbeat_at: datetime | None
    bed_id: UUID | None
    bed_label: str | None
    ward_id: UUID | None


class AssignMonitor(Strict):
    bed_id: UUID
    confirm: StrictBool
    # Per-device secret printed on the monitor label (T425/T426); verified (hashed, throttled) in the database.
    pairing_code: Annotated[str, Field(min_length=16, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")]


    @model_validator(mode="after")
    def _confirmed(self) -> AssignMonitor:
        if not self.confirm:
            raise ValueError("binding a monitor to a bed requires explicit confirmation")
        return self


class MaintenanceKind(StrEnum):
    inspection = "inspection"
    calibration = "calibration"
    battery_replacement = "battery_replacement"
    repair = "repair"
    firmware_update = "firmware_update"


class MaintenanceIn(Strict):
    kind: MaintenanceKind
    notes: Annotated[CleanText, Field(max_length=1000)] = ""
    next_due: date | None = None

    @model_validator(mode="after")
    def _plausible_due_date(self) -> MaintenanceIn:
        if self.next_due is not None:
            today = datetime.now(UTC).date()
            if not (today <= self.next_due <= today + timedelta(days=5 * 366)):
                raise ValueError("next_due must be between today and five years from now")
        return self


class MaintenanceOut(Out):
    id: UUID
    monitor_id: UUID
    kind: str
    notes: str
    performed_by_name: str
    performed_at: datetime
    next_due: date | None


# ---------- staff ----------
class StaffOut(Out):
    user_id: UUID
    email: str
    full_name: str
    role: RoleName
    is_active: bool
    ward_ids: list[UUID]
    last_login_at: datetime | None


class StaffInvite(Strict):
    email: StaffEmail
    full_name: PersonName
    role: RoleName
    ward_ids: Annotated[list[UUID], Field(max_length=10)] = []


class StaffUpdate(Strict):
    role: RoleName | None = None
    is_active: StrictBool | None = None
    ward_ids: Annotated[list[UUID], Field(max_length=10)] | None = None


# ---------- settings ----------
class SecuritySettingsOut(Out):
    password_min_length: int
    session_idle_minutes: int
    session_absolute_hours: int
    max_concurrent_sessions: int
    lockout_threshold: int
    lockout_minutes: int
    require_mfa_for_admin: bool
    data_retention_days: int
    updated_at: datetime


class SecuritySettingsUpdate(Strict):
    password_min_length: bounded_int(12, 128) | None = None
    session_idle_minutes: bounded_int(5, 60) | None = None
    session_absolute_hours: bounded_int(1, 24) | None = None
    max_concurrent_sessions: bounded_int(1, 10) | None = None
    lockout_threshold: bounded_int(3, 10) | None = None
    lockout_minutes: bounded_int(5, 120) | None = None
    require_mfa_for_admin: StrictBool | None = None
    data_retention_days: bounded_int(30, 3650) | None = None


# ---------- simulation / events / break glass / files ----------
class SimulationOut(Out):
    scenario: Scenario
    tick: int
    version: int
    updated_at: datetime


class SimulationScenarioIn(Strict):
    scenario: Scenario
    monitor_ids: Annotated[list[UUID], Field(max_length=10)] = []


class SimulationAdvanceIn(Strict):
    steps: bounded_int(1, 60) = 1
    expected_version: bounded_int(0, 2_147_483_647)


class SimulationResetIn(Strict):
    confirm_text: Annotated[str, Field(max_length=40)]

    @model_validator(mode="after")
    def _typed(self) -> SimulationResetIn:
        if self.confirm_text != "RESET DEMO DATA":
            raise ValueError("type RESET DEMO DATA to confirm")
        return self


class EventOut(Out):
    id: int
    occurred_at: datetime
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str | None
    outcome: str
    details: dict


class BreakGlassIn(Strict):
    patient_id: UUID
    reason: Annotated[CleanText, Field(min_length=10, max_length=500)]


class BreakGlassOut(Out):
    id: UUID
    patient_id: UUID
    expires_at: datetime


class AttachmentOut(Out):
    id: UUID
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class SignedUrlOut(Out):
    url: str
    expires_in: int


class ReportOut(Out):
    ward_id: UUID | None
    period_start: datetime
    period_end: datetime
    alarm_counts: dict[str, int | None]  # None = suppressed small count
    mean_time_to_ack_seconds: float | None
    unacknowledged_high_priority: int
    readings_count: int
    generated_at: datetime
