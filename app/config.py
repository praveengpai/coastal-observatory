"""Settings, all read from environment variables (see .env.example)."""
import os


def _env(name, default=None, cast=str):
    val = os.environ.get(name, default)
    return cast(val) if val is not None else None


DATABASE_URL = _env("OBS_DATABASE_URL", "sqlite:///./observatory.db")
SECRET_KEY = _env("OBS_SECRET_KEY", "change-me-in-production-at-least-32-characters")
TOKEN_HOURS = _env("OBS_TOKEN_HOURS", "8", int)
ENVIRONMENT = _env("OBS_ENVIRONMENT", "development")  # development | staging | production

FORM_SERVER = _env("OBS_FORM_SERVER", "odk")   # odk (ODK Central) | kobo (KoboToolbox)

# ODK Central
ODK_URL = _env("OBS_ODK_URL", "")          # e.g. https://odk.example.org
ODK_PROJECT_ID = _env("OBS_ODK_PROJECT_ID", "1", int)
ODK_EMAIL = _env("OBS_ODK_EMAIL", "")
ODK_PASSWORD = _env("OBS_ODK_PASSWORD", "")

# Weather (Open-Meteo, no key needed). Default: Kochi.
WEATHER_LAT = _env("OBS_WEATHER_LAT", "9.9816", float)
WEATHER_LON = _env("OBS_WEATHER_LON", "76.2999", float)

# Model coefficients: priors until refitted on Phase 1 data (tools/fit_model.py writes these).
MODEL = {
    "intercept": float(_env("OBS_M_INTERCEPT", "-5.0")),
    "rain_mm": float(_env("OBS_M_RAIN", "0.025")),
    "tide_m_above_0_8": float(_env("OBS_M_TIDE", "2.0")),
    "temp_c_above_28": float(_env("OBS_M_TEMP", "0.12")),
}

# Thresholds for risk levels
POSITIVITY_WATCH, POSITIVITY_HIGH = 0.15, 0.35
TDS_WATCH, TDS_HIGH = 500, 1000
ILLNESS_WATCH, ILLNESS_HIGH = 10.0, 25.0      # diarrhoea reports per 100 households visited, 4 weeks
VULN_WATCH, VULN_HIGH = 0.20, 0.40            # share of 60+ who live alone, need evacuation help or are frail
HEAT_WATCH, HEAT_HIGH = 32, 41                # heat index °C
TIDE_ALERT_M = 1.3
RAIN_ALERT_MM = 64.5                          # IMD "heavy rain" threshold per day

TEST_SITE_TYPES = {"test"}                    # excluded from analytics unless ?include_test=1
