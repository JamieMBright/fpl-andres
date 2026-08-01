"""What produced a decision, recorded alongside it.

Audit item #197. `model_promotion_decisions` recorded the seed, the resample
count and the sample size — enough to re-run the bootstrap, and not enough to
reproduce the answer. Re-running it needs three more things:

- **which code**, because a change to the metric changes the number;
- **which corpus**, because it is a mutable table and a re-ingest that corrects
  one fixture moves every metric derived from it;
- **which numerical libraries**, because scipy's `spearmanr` and HiGHS' simplex
  are the parts doing the arithmetic, and neither promises bit-identical results
  across versions.

A promotion that cannot be reproduced is not evidence, it is a number someone
wrote down.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from importlib import metadata

from fpl_andres import timeouts
from fpl_andres.persistence.backtest import RevisionUnavailable

__all__ = ["NUMERICAL_DEPENDENCIES", "Lineage", "capture_lineage", "dependency_fingerprint"]

# The libraries whose version can change a result. Not every dependency: httpx
# moving does not alter a rank correlation, and a fingerprint that changes for
# reasons that cannot affect the number it guards gets ignored.
NUMERICAL_DEPENDENCIES = ("numpy", "scipy", "highspy", "pydantic")


@dataclass(frozen=True)
class Lineage:
    """Everything needed to reproduce a decision, other than the seed."""

    code_revision: str
    dependency_fingerprint: str
    dependency_versions: tuple[str, ...]
    corpus_fingerprint: str | None = None


def dependency_fingerprint() -> tuple[str, tuple[str, ...]]:
    """A hash of the installed numerical library versions, and the list itself.

    The list is kept as well as the hash: a hash tells you two runs differed,
    and the list tells you how.
    """
    versions: list[str] = []
    for name in NUMERICAL_DEPENDENCIES:
        try:
            versions.append(f"{name}=={metadata.version(name)}")
        except metadata.PackageNotFoundError:
            # Absent is itself a fact about the environment, and one that would
            # otherwise make two different environments fingerprint alike.
            versions.append(f"{name}==absent")
    digest = hashlib.sha256("|".join(versions).encode("utf-8")).hexdigest()
    return f"sha256:{digest}", tuple(versions)


def capture_lineage(*, corpus_fingerprint: str | None = None) -> Lineage:
    """Read the lineage of the run that is about to produce a decision.

    Fails rather than defaulting. A decision attributed to an unknown revision
    cannot be compared to anything, so an unlabelled one is worse than none.
    """
    fingerprint, versions = dependency_fingerprint()
    return Lineage(
        code_revision=_current_revision(),
        dependency_fingerprint=fingerprint,
        dependency_versions=versions,
        corpus_fingerprint=corpus_fingerprint,
    )


def _current_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeouts.SUBPROCESS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RevisionUnavailable("could not read the current git revision") from error

    revision = result.stdout.strip()
    if not revision:
        raise RevisionUnavailable("git reported an empty revision")
    return revision
