"""LinkedIn DOM selector constants with fallbacks.

Ordered by stability: data-* > aria-* > class names (L4).
Each constant is a tuple so callers iterate until a match is found.
"""

# --- Job card container ---
CARD_SELECTORS: tuple[str, ...] = (
    "li[data-occludable-job-id]",
    "li.jobs-search-results__list-item",
    "li.scaffold-layout__list-item",
)

# --- Job ID attributes on the card element ---
JOB_ID_ATTR: str = "data-occludable-job-id"
JOB_ID_ATTR_FALLBACK: str = "data-job-id"

# --- Title link inside a card ---
TITLE_LINK_SELECTORS: tuple[str, ...] = (
    'a[href*="/jobs/view/"]',
    "a.job-card-list__title",
    "a.job-card-container__link",
)

# --- Company name ---
COMPANY_SELECTORS: tuple[str, ...] = (
    "span.job-card-container__primary-description",
    ".artdeco-entity-lockup__subtitle",
    "span.job-card-container__company-name",
)

# --- Location ---
LOCATION_SELECTORS: tuple[str, ...] = (
    "li.job-card-container__metadata-item",
    ".artdeco-entity-lockup__caption",
    "span.job-card-container__metadata-wrapper",
)

# --- Posted time ---
POSTED_TIME_SELECTORS: tuple[str, ...] = (
    "time",
    "span.job-card-container__listed-time",
    ".job-card-container__footer-item",
)

# --- No results indicator ---
NO_RESULTS_SELECTORS: tuple[str, ...] = (
    ".jobs-search-no-results-banner",
    ".jobs-search-results-list__subtitle--no-results",
)
