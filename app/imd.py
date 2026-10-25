"""IMD (India Meteorological Department) connector: waiting for API access.

IMD shares its APIs with registered organisations (https://api.imd.gov.in/; nodal officer listed in
IMD's API document). Once access is granted, put the key in .env as OBS_IMD_API_KEY and the endpoint
details IMD provides in OBS_IMD_BASE_URL and OBS_IMD_DISTRICT (Ernakulam's IMD district code), then
complete `fetch` below against IMD's own API reference. Until then the Data sources panel shows
"Waiting for IMD API access" and nothing is called.
"""
import os


class NotReady(RuntimeError):
    pass


def enabled() -> bool:
    return bool(os.environ.get("OBS_IMD_API_KEY"))


def fetch(db) -> str:
    if not enabled():
        raise NotReady("IMD API access is not set up yet. Apply at api.imd.gov.in, then add OBS_IMD_API_KEY to .env.")
    if not os.environ.get("OBS_IMD_BASE_URL"):
        raise NotReady("IMD key found, but OBS_IMD_BASE_URL is not set. Add the endpoint from IMD's API reference.")
    # Deliberately not guessed: the request format must follow the API reference IMD issues with the key.
    raise NotReady("IMD key and address found. The connector will be completed from IMD's API reference.")
