"""Schema-validated access to FPL's `bootstrap-static` elements.

Audit item #139. The publishers read upstream fields with bare casts —
`int(element["id"])`, `float(element["selected_by_percent"])` — which fail in the
two worst ways available. A missing key raises `KeyError: 'id'` naming neither
the player nor the endpoint. A `None` raises `TypeError: int() argument must be
a string...`, which reads like a bug in this repository rather than a change at
FPL's end.

The repository rule is to fail a source contract visibly. A cast is a silent
contract: it asserts a type without saying so, and produces a message no one can
act on when the assertion breaks.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from fpl_andres.positions import Position

__all__ = [
    "BootstrapElement",
    "BootstrapElementError",
    "CrowdElement",
    "OwnershipElement",
    "parse_elements",
]


class BootstrapElementError(ValueError):
    """Raised when bootstrap-static carries an element this package cannot read."""


class CrowdElement(BaseModel):
    """What a crowd-ownership capture reads: who, and how many own him.

    `selected_by_percent` is required, not defaulted. A default would turn a
    field FPL stopped sending into a player nobody owns, which is a plausible
    reading of the number and a wrong one. `test_fplcache` has asserted this
    since the adapter was written: a missing ownership is refused, not zeroed.

    Transfer counts stay optional because an archived capture legitimately
    predates them, and `None` says "not captured" where `0` would claim nobody
    moved.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: Annotated[int, Field(gt=0)]
    # Arrives as a string like "30.4".
    selected_by_percent: Annotated[float, Field(ge=0.0, le=100.0)]
    transfers_in_event: Annotated[int, Field(ge=0)] | None = None
    transfers_out_event: Annotated[int, Field(ge=0)] | None = None


class OwnershipElement(CrowdElement):
    """Adds the identity and price an archived snapshot must carry.

    Separate from `BootstrapElement` so a snapshot missing a field that ownership
    ingestion never reads does not break ownership ingestion. Requiring `status`
    in order to record a price would be a coupling invented here rather than one
    FPL imposed.
    """

    code: Annotated[int, Field(gt=0)]
    # FPL prices in tenths. 200 is a 20.0m player; nothing has ever come close,
    # but the ceiling is the squad budget so anything above it is a broken feed.
    now_cost: Annotated[int, Field(gt=0, le=1000)]
    transfers_in_event: Annotated[int, Field(ge=0)]
    transfers_out_event: Annotated[int, Field(ge=0)]


class BootstrapElement(OwnershipElement):
    """One player in `bootstrap-static.elements`.

    Not `extra="forbid"`: FPL adds fields between seasons and this package has no
    business refusing a payload because it grew. Only the fields actually used
    are declared, and each one is constrained to the range that makes it usable.
    """

    element_type: int
    team: Annotated[int, Field(gt=0, le=20)]
    web_name: Annotated[str, Field(min_length=1, max_length=100)]
    # a=available, d=doubtful, i=injured, s=suspended, u=unavailable, n=not in squad
    status: Annotated[str, Field(min_length=1, max_length=1)]

    @property
    def position(self) -> Position:
        """Refuses an element type outside the four positions.

        Validated here rather than as a field constraint so the caller can skip
        an unknown type deliberately, which is what the publishers do: FPL has
        shipped a fifth element type before (Assistant Manager, 2024/25).
        """
        return Position(self.element_type)

    @property
    def is_available(self) -> bool:
        """FPL's own flag. Injured, suspended and departed players are not picks."""
        return self.status == "a"


def parse_elements[ElementT: CrowdElement](
    payload: Any,
    *,
    model: type[ElementT],
    source: str = "bootstrap-static",
) -> list[ElementT]:
    """Validate every element, naming the player and the field when one fails.

    Refuses the whole payload rather than dropping the bad row. A publisher that
    silently skipped a malformed element would ship a squad chosen from an
    incomplete pool and say nothing about it.
    """
    if not isinstance(payload, list):
        raise BootstrapElementError(
            f"{source} elements must be a list, got {type(payload).__name__}"
        )
    elements: list[ElementT] = []
    for index, raw in enumerate(payload):
        try:
            elements.append(model.model_validate(raw))
        except ValidationError as error:
            identity = ""
            if isinstance(raw, dict):
                identity = f" (id={raw.get('id')!r}, web_name={raw.get('web_name')!r})"
            raise BootstrapElementError(
                f"{source} elements[{index}]{identity} does not match the expected "
                f"contract: {error.errors(include_url=False)}"
            ) from error
    if not elements:
        raise BootstrapElementError(f"{source} returned no elements")
    return elements
