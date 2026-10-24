"""Daily weather forecast (Open-Meteo, free, no key) and tide table import."""
import csv
import io
from datetime import date

import requests
from sqlalchemy.orm import Session

from . import config
from .models import Weather

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


def fetch_forecast(db: Session, lat=None, lon=None, days=7) -> int:
    params = {
        "latitude": lat or config.WEATHER_LAT, "longitude": lon or config.WEATHER_LON,
        "daily": "precipitation_sum,temperature_2m_max,relative_humidity_2m_mean",
        "timezone": "Asia/Kolkata", "forecast_days": days,
    }
    r = requests.get(OPEN_METEO, params=params, timeout=30)
    r.raise_for_status()
    d = r.json()["daily"]
    for i, day in enumerate(d["time"]):
        w = db.get(Weather, date.fromisoformat(day)) or Weather(day=date.fromisoformat(day))
        w.rain_mm = d["precipitation_sum"][i]
        w.temp_max = d["temperature_2m_max"][i]
        w.rh_mean = d["relative_humidity_2m_mean"][i]
        db.merge(w)
    db.commit()
    return len(d["time"])


def import_tides(db: Session, text: str) -> int:
    """CSV with columns: date (YYYY-MM-DD), high_tide_m. NIO or the Port tide tables can supply this."""
    n = 0
    for row in csv.DictReader(io.StringIO(text)):
        day = date.fromisoformat(row["date"].strip())
        w = db.get(Weather, day) or Weather(day=day)
        w.tide_max_m = float(row["high_tide_m"])
        db.merge(w)
        n += 1
    db.commit()
    return n
