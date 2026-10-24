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
    role: Mapped[str] = mapped_column(String(12))     # admin | coordinator | scientist | doctor | asha | ward
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
