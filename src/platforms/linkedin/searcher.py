"""LinkedIn URL builder and pagination helpers.

Pure functions — zero browser dependency.
"""

import logging
from urllib.parse import quote_plus, urlencode

from src.core.config import SearchFilters

logger = logging.getLogger(__name__)

RESULTS_PER_PAGE = 25

# --- Mapping dicts (URL concern) ---

WORKPLACE_TYPE_MAP: dict[str, str] = {
    "remote": "2",
    "hybrid": "3",
    "onsite": "1",
    "on-site": "1",
}

EXPERIENCE_LEVEL_MAP: dict[str, str] = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "senior": "4",
    "director": "5",
    "executive": "6",
}


def build_url(keyword: str, filters: SearchFilters, page: int = 0) -> str:
    """Build a LinkedIn jobs search URL from keyword, filters, and page number.

    Args:
        keyword: Search keyword (will be URL-encoded).
        filters: SearchFilters instance with geo_id, workplace_type, etc.
        page: Zero-based page number. page=0 omits ``start`` param.

    Returns:
        Fully qualified LinkedIn search URL.
    """
    base = "https://www.linkedin.com/jobs/search/"
    params: dict[str, str] = {
        "keywords": keyword,
        "sortBy": "DD",
    }

    if filters.geo_id is not None:
        params["geoId"] = str(filters.geo_id)

    if filters.easy_apply_only:
        params["f_AL"] = "true"

    # Workplace type: comma-separated codes
    wt_codes = _map_values(filters.workplace_type, WORKPLACE_TYPE_MAP, "workplace_type")
    if wt_codes:
        params["f_WT"] = ",".join(wt_codes)

    # Experience level: comma-separated codes
    exp_codes = _map_values(filters.experience_level, EXPERIENCE_LEVEL_MAP, "experience_level")
    if exp_codes:
        params["f_E"] = ",".join(exp_codes)

    if page > 0:
        params["start"] = str(page * RESULTS_PER_PAGE)

    return f"{base}?{urlencode(params, quote_via=quote_plus)}"


def should_stop_pagination(cards_found: int, page: int) -> bool:
    """Return True if we should stop paginating.

    LinkedIn serves 25 results per page (L8). Fewer than 25 means last page.
    """
    return cards_found < RESULTS_PER_PAGE


def build_job_url(job_id: str) -> str:
    """Build a canonical LinkedIn job detail URL."""
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def _map_values(
    values: list[str],
    mapping: dict[str, str],
    field_name: str,
) -> list[str]:
    """Map user-facing filter values to LinkedIn URL codes.

    Unknown values are logged and skipped (never crash).
    """
    codes: list[str] = []
    for v in values:
        key = v.lower().strip()
        code = mapping.get(key)
        if code is None:
            logger.warning("Unknown %s value '%s' — skipping", field_name, v)
        else:
            codes.append(code)
    return codes
