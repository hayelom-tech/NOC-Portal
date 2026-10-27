REGION_NAMES = (
    "East 1",
    "East 2",
    "West",
    "North West",
    "North East",
    "North",
    "Afar",
)

_REGION_NAMES_BY_KEY = {name.casefold(): name for name in REGION_NAMES}


def canonical_region_name(value: str) -> str | None:
    return _REGION_NAMES_BY_KEY.get(value.strip().casefold())
