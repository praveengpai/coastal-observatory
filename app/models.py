"""Database tables.

Identifiable data (names, phones, addresses) lives ONLY in person_pii, which only
admin, coordinator, doctor and ASHA roles can read. Everything else is keyed by
sticker IDs (person OBS-P-000123, household CVB-014, sample WS-000123).
"""
from datetime import datetime, date

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Site(Base):
    __tablename__ = "site"
    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    site_type: Mapped[str] = mapped_column(String(20))        # village | colony | flats | ward | test
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Household(Base):
    __tablename__ = "household"
    hh_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    site_code: Mapped[str] = mapped_column(ForeignKey("site.code"), index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)


class Person(Base):
    __tablename__ = "person"
    person_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    hh_id: Mapped[str | None] = mapped_column(String(16), index=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    sex: Mapped[str | None] = mapped_column(String(2))
    age: Mapped[int | None] = mapped_column(Integer)
    resident: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_research: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_on: Mapped[date | None] = mapped_column(Date)


class PersonPII(Base):
    __tablename__ = "person_pii"
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(15))
    contact_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    home_address: Mapped[str | None] = mapped_column(Text)


class Registration(Base):
    __tablename__ = "registration"
    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(16), index=True)
    hh_id: Mapped[str | None] = mapped_column(String(16), index=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    camp_id: Mapped[str | None] = mapped_column(String(24), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    collected_on: Mapped[date | None] = mapped_column(Date, index=True)
    age: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(2))
    occupation: Mapped[str | None] = mapped_column(String(20))
    symptoms: Mapped[str | None] = mapped_column(String(200))      # space-separated
    conditions: Mapped[str | None] = mapped_column(String(200))
    tobacco: Mapped[str | None] = mapped_column(String(10))
    wade: Mapped[bool | None] = mapped_column(Boolean)
    data: Mapped[dict] = mapped_column(JSON, default=dict)      # full submission minus PII


class HouseholdSurvey(Base):
    __tablename__ = "household_survey"
    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hh_id: Mapped[str] = mapped_column(String(16), index=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    collected_on: Mapped[date | None] = mapped_column(Date)
    hh_size: Mapped[int | None] = mapped_column(Integer)
    hh_n60: Mapped[int | None] = mapped_column(Integer)
    hh_n5: Mapped[int | None] = mapped_column(Integer)
    water_drink: Mapped[str | None] = mapped_column(String(20))
    treat: Mapped[str | None] = mapped_column(String(100))
    storage: Mapped[str | None] = mapped_column(String(20))
    salty: Mapped[str | None] = mapped_column(String(12))
    toilet: Mapped[str | None] = mapped_column(String(12))
    septic_dist: Mapped[str | None] = mapped_column(String(8))
    flood: Mapped[bool | None] = mapped_column(Boolean)
    flood_times: Mapped[int | None] = mapped_column(Integer)
    animals: Mapped[str | None] = mapped_column(String(100))
    rats: Mapped[str | None] = mapped_column(String(12))
    tds: Mapped[int | None] = mapped_column(Integer)


class StationRecord(Base):
    __tablename__ = "station_record"
    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(16), index=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    camp_id: Mapped[str | None] = mapped_column(String(24))
    station: Mapped[str] = mapped_column(String(10), index=True)  # meas | eye | dental | geri | doctor
    collected_on: Mapped[date | None] = mapped_column(Date)
    age: Mapped[int | None] = mapped_column(Integer)
    # measurements
    sbp: Mapped[float | None] = mapped_column(Float)
    dbp: Mapped[float | None] = mapped_column(Float)
    glucose: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    u_protein: Mapped[str | None] = mapped_column(String(6))
    u_sg: Mapped[float | None] = mapped_column(Float)
    hb: Mapped[float | None] = mapped_column(Float)
    # eye
    va_r: Mapped[str | None] = mapped_column(String(8))
    va_l: Mapped[str | None] = mapped_column(String(8))
    cataract: Mapped[str | None] = mapped_column(String(6))
    dr_worst: Mapped[str | None] = mapped_column(String(12))
    # dental
    caries_n: Mapped[int | None] = mapped_column(Integer)
    lesion: Mapped[str | None] = mapped_column(String(10))
    # geriatric
    alone: Mapped[bool | None] = mapped_column(Boolean)
    evac: Mapped[bool | None] = mapped_column(Boolean)
    heat_sx: Mapped[bool | None] = mapped_column(Boolean)
    falls: Mapped[int | None] = mapped_column(Integer)
    cfs: Mapped[int | None] = mapped_column(Integer)
    minicog: Mapped[int | None] = mapped_column(Integer)
    phq2: Mapped[int | None] = mapped_column(Integer)
    # any station
    referral: Mapped[str | None] = mapped_column(String(20))
    followup: Mapped[bool | None] = mapped_column(Boolean)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class WaterSample(Base):
    __tablename__ = "water_sample"
    sample_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    instance_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    hh_id: Mapped[str | None] = mapped_column(String(16), index=True)
    point_type: Mapped[str | None] = mapped_column(String(12))
    source: Mapped[str | None] = mapped_column(String(16))
    taken_at: Mapped[str | None] = mapped_column(String(8))
    collected_on: Mapped[date | None] = mapped_column(Date, index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    tds: Mapped[int | None] = mapped_column(Integer)
    water_temp: Mapped[float | None] = mapped_column(Float)
    rain_48h: Mapped[bool | None] = mapped_column(Boolean)
    flooded_7d: Mapped[bool | None] = mapped_column(Boolean)
    to_lab: Mapped[bool | None] = mapped_column(Boolean)


class LabResult(Base):
    __tablename__ = "lab_result"
    __table_args__ = (UniqueConstraint("sample_id", "method"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_id: Mapped[str] = mapped_column(String(12), index=True)
    method: Mapped[str] = mapped_column(String(10))            # aquadip | nio_lab
    positive: Mapped[bool | None] = mapped_column(Boolean)
    ecoli_cfu: Mapped[float | None] = mapped_column(Float)     # per 100 mL
    coliform_cfu: Mapped[float | None] = mapped_column(Float)
    vibrio: Mapped[str | None] = mapped_column(String(20))      # detected | not_detected | species name
    amr_note: Mapped[str | None] = mapped_column(String(200))
    tested_on: Mapped[date | None] = mapped_column(Date)


class HomeVisit(Base):
    __tablename__ = "home_visit"
    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hh_id: Mapped[str] = mapped_column(String(16), index=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    visit_on: Mapped[date | None] = mapped_column(Date, index=True)
    role: Mapped[str | None] = mapped_column(String(12))
    reason: Mapped[str | None] = mapped_column(String(100))
    n_diarrhoea: Mapped[int] = mapped_column(Integer, default=0)
    n_diarrhoea_u5: Mapped[int] = mapped_column(Integer, default=0)
    n_fever: Mapped[int] = mapped_column(Integer, default=0)
    n_jaundice: Mapped[int] = mapped_column(Integer, default=0)
    n_skin: Mapped[int] = mapped_column(Integer, default=0)
    n_eye: Mapped[int] = mapped_column(Integer, default=0)
    n_wound: Mapped[int] = mapped_column(Integer, default=0)
    n_heat: Mapped[int] = mapped_column(Integer, default=0)
    n_hosp: Mapped[int] = mapped_column(Integer, default=0)
    ref_person: Mapped[str | None] = mapped_column(String(16), index=True)
    ref_status: Mapped[str | None] = mapped_column(String(10))
    eld_evac: Mapped[bool | None] = mapped_column(Boolean)
    advice: Mapped[str | None] = mapped_column(String(100))


class Weather(Base):
    __tablename__ = "weather"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    rain_mm: Mapped[float | None] = mapped_column(Float)
    temp_max: Mapped[float | None] = mapped_column(Float)
    rh_mean: Mapped[float | None] = mapped_column(Float)
    tide_max_m: Mapped[float | None] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Decision(Base):
    __tablename__ = "decision"
    __table_args__ = (UniqueConstraint("rule_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(80))
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    title: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="open")   # open | approved | declined
    decided_by: Mapped[str | None] = mapped_column(String(60))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)


class Advisory(Base):
    __tablename__ = "advisory"
    __table_args__ = (UniqueConstraint("rule_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(80))
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    hh_id: Mapped[str | None] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(20))
    text_en: Mapped[str] = mapped_column(Text)
    text_ml: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft")   # draft | approved | sent | rejected
    reviewed_by: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "app_user"
    username: Mapped[str] = mapped_column(String(60), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(12))     # admin coordinator scientist doctor asha ward jphn mo dso lab
    sites: Mapped[str] = mapped_column(String(200), default="*")   # space-separated site codes or *
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    username: Mapped[str | None] = mapped_column(String(60))
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(300))
    status: Mapped[int] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(45))


class SyncState(Base):
    __tablename__ = "sync_state"
    form_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    last_submission: Mapped[str | None] = mapped_column(String(40))
    last_run: Mapped[datetime | None] = mapped_column(DateTime)
    count: Mapped[int] = mapped_column(Integer, default=0)


class ReportForm(Base):
    """A household report form (form ID starting obs_report_) and which dashboard roles may see its reports."""
    __tablename__ = "report_form"
    form_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    visible_roles: Mapped[str] = mapped_column(String(120), default="admin coordinator doctor asha")
    phone_groups: Mapped[str] = mapped_column(String(400), default="")     # display only: who can fill it
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Report(Base):
    """One household report. Names live in person_pii; this row holds no direct identifiers."""
    __tablename__ = "report"
    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    form_id: Mapped[str] = mapped_column(String(60), index=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    hh_id: Mapped[str | None] = mapped_column(String(16), index=True)
    person_id: Mapped[str | None] = mapped_column(String(16), index=True)
    named: Mapped[bool] = mapped_column(Boolean, default=False)
    reporter_role: Mapped[str | None] = mapped_column(String(12))
    reported_on: Mapped[date | None] = mapped_column(Date, index=True)
    onset: Mapped[date | None] = mapped_column(Date)
    age: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(2))
    condition: Mapped[str | None] = mapped_column(String(20), index=True)
    water_class: Mapped[str | None] = mapped_column(String(16), index=True)  # water_borne | water_washed | water_contact | vector
    danger: Mapped[bool | None] = mapped_column(Boolean)
    days_ill: Mapped[int | None] = mapped_column(Integer)
    activity: Mapped[str | None] = mapped_column(String(12))
    work_days: Mapped[int] = mapped_column(Integer, default=0)
    school_days: Mapped[int] = mapped_column(Integer, default=0)
    carer_days: Mapped[int] = mapped_column(Integer, default=0)
    care: Mapped[str | None] = mapped_column(String(10))
    cost_rs: Mapped[int | None] = mapped_column(Integer)
    events: Mapped[str | None] = mapped_column(String(200))       # One Health events, space-separated
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class IdspCase(Base):
    """One illness episode in the IDSP module: one person, one syndrome, one onset (within 14 days).

    Every report about the same episode, from IDSP staff or from the community, joins the same row,
    so a case is counted once however many people report it. Only VERIFIED cases count as IDSP data.
    No names here: they stay in person_pii.
    """
    __tablename__ = "idsp_case"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    hh_id: Mapped[str | None] = mapped_column(String(16), index=True)
    person_id: Mapped[str | None] = mapped_column(String(16), index=True)
    age: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(2))
    syndrome: Mapped[str] = mapped_column(String(20), index=True)      # IHIP Form S syndrome code
    suspect: Mapped[str | None] = mapped_column(String(20))            # e.g. cholera, typhoid, lepto, dengue
    status: Mapped[str] = mapped_column(String(12), default="unverified", index=True)
    # unverified | verified | not_case | duplicate | unreachable
    first_source: Mapped[str] = mapped_column(String(10))              # community | camp | idsp
    sources: Mapped[str] = mapped_column(String(60), default="")       # every source that reported it
    reporter_roles: Mapped[str] = mapped_column(String(80), default="")
    onset: Mapped[date | None] = mapped_column(Date)
    first_reported: Mapped[date | None] = mapped_column(Date, index=True)
    idsp_reported: Mapped[date | None] = mapped_column(Date)           # first IDSP Form S entry for it
    verified_on: Mapped[date | None] = mapped_column(Date, index=True)
    verified_by: Mapped[str | None] = mapped_column(String(60))
    verify_note: Mapped[str | None] = mapped_column(String(300))
    duplicate_of: Mapped[int | None] = mapped_column(Integer)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)       # danger signs, admitted, death, under-5 dysentery
    admitted: Mapped[bool] = mapped_column(Boolean, default=False)
    died: Mapped[bool] = mapped_column(Boolean, default=False)
    water_source: Mapped[str | None] = mapped_column(String(20))
    work_days: Mapped[int] = mapped_column(Integer, default=0)
    carer_days: Mapped[int] = mapped_column(Integer, default=0)
    school_days: Mapped[int] = mapped_column(Integer, default=0)
    p_diagnosis: Mapped[str | None] = mapped_column(String(20))        # IHIP Form P disease code
    p_by: Mapped[str | None] = mapped_column(String(60))
    p_on: Mapped[date | None] = mapped_column(Date)
    lab_test: Mapped[str | None] = mapped_column(String(20))
    lab_result: Mapped[str | None] = mapped_column(String(10))         # positive | negative | pending
    lab_sample_id: Mapped[str | None] = mapped_column(String(40))
    lab_sample_on: Mapped[date | None] = mapped_column(Date)
    lab_on: Mapped[date | None] = mapped_column(Date)
    lab_by: Mapped[str | None] = mapped_column(String(60))


class IdspOrigin(Base):
    """Which source record (form submission) fed which case. Makes signal capture idempotent."""
    __tablename__ = "idsp_origin"
    key: Mapped[str] = mapped_column(String(90), primary_key=True)     # "<kind>:<instance id>"
    case_id: Mapped[int | None] = mapped_column(Integer, index=True)   # None: looked at, not an IDSP syndrome
    kind: Mapped[str] = mapped_column(String(10))                      # community | camp | idsp
    reported_on: Mapped[date | None] = mapped_column(Date, index=True)
    site_code: Mapped[str | None] = mapped_column(String(8), index=True)
    role: Mapped[str | None] = mapped_column(String(12))


class IdspNil(Base):
    """A nil report: an IDSP worker saying 'no cases of any listed syndrome in my area this week'."""
    __tablename__ = "idsp_nil"
    instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    reported_on: Mapped[date | None] = mapped_column(Date)
    role: Mapped[str | None] = mapped_column(String(12))


class IdspAlert(Base):
    """An early-warning alert with a named owner and a closure, so response times can be measured."""
    __tablename__ = "idsp_alert"
    __table_args__ = (UniqueConstraint("rule_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(100))
    site_code: Mapped[str] = mapped_column(String(8), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))                  # immediate | high | watch
    title: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(500))
    send_to: Mapped[str] = mapped_column(String(80))
    response: Mapped[str] = mapped_column(String(200))
    case_ids: Mapped[str] = mapped_column(String(400), default="")
    links: Mapped[dict] = mapped_column(JSON, default=dict)            # water sources linked to the cases
    status: Mapped[str] = mapped_column(String(12), default="open")    # open | acknowledged | closed
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ack_by: Mapped[str | None] = mapped_column(String(60))
    ack_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by: Mapped[str | None] = mapped_column(String(60))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    action_taken: Mapped[str | None] = mapped_column(String(500))


class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str | None] = mapped_column(String(200))


class SourceStatus(Base):
    """When each outside data source last answered, for the Admin tab's Data sources panel."""
    __tablename__ = "source_status"
    key: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime)
    last_ok: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(300))
    detail: Mapped[str | None] = mapped_column(String(300))
