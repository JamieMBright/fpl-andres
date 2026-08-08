"""CLI arguments must be refused before the work starts.

Every numeric argument was `type=int` or `type=float`, so
`--rate 0` reached the throttle and divided by zero, `--concurrency 0` produced a
semaphore nobody could acquire, and `--gameweek 99` ran a whole ingest before
failing on a database check constraint.

Argparse reports these as usage errors with exit status 2, naming the flag,
which is what a wrong flag deserves rather than a traceback from four layers
down.
"""

from __future__ import annotations

import argparse

import pytest

from fpl_andres import cliargs


@pytest.mark.parametrize("raw", ["1", "8", "2500000"])
def test_a_positive_whole_number_is_accepted(raw: str) -> None:
    assert cliargs.positive_int(raw) == int(raw)


@pytest.mark.parametrize("raw", ["0", "-1", "-2500000"])
def test_a_non_positive_count_is_refused(raw: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="at least 1"):
        cliargs.positive_int(raw)


@pytest.mark.parametrize("raw", ["", "eight", "8.5", "0x10"])
def test_a_non_integer_count_says_so(raw: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="not a whole number"):
        cliargs.positive_int(raw)


def test_python_underscores_in_a_number_are_accepted() -> None:
    """`int("1_000")` is legal Python and reads clearly on a command line."""
    assert cliargs.positive_int("2_500_000") == 2_500_000


@pytest.mark.parametrize("raw", ["0.5", "25", "1e3"])
def test_a_positive_rate_is_accepted(raw: str) -> None:
    assert cliargs.positive_float(raw) == float(raw)


@pytest.mark.parametrize("raw", ["0", "0.0", "-1", "-0.001"])
def test_a_non_positive_rate_is_refused(raw: str) -> None:
    """`--rate 0` divided by zero inside the throttle."""
    with pytest.raises(argparse.ArgumentTypeError, match="greater than 0"):
        cliargs.positive_float(raw)


@pytest.mark.parametrize("raw", ["inf", "Infinity"])
def test_an_infinite_rate_is_refused(raw: str) -> None:
    """float() accepts these. A throttle interval of 1/inf is zero delay."""
    with pytest.raises(argparse.ArgumentTypeError, match="finite"):
        cliargs.positive_float(raw)


def test_a_nan_rate_is_refused() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="finite"):
        cliargs.positive_float("nan")


@pytest.mark.parametrize("raw", ["1", "38", "47"])
def test_a_real_gameweek_is_accepted(raw: str) -> None:
    assert cliargs.event_id(raw) == int(raw)


@pytest.mark.parametrize("raw", ["0", "48", "99", "-1"])
def test_an_impossible_gameweek_is_refused(raw: str) -> None:
    """The ceiling is 47 rather than 38: 2019/20 ran to 47 after the pandemic
    restart, and the database check constraint uses the same bound."""
    with pytest.raises(argparse.ArgumentTypeError, match=r"gameweek 1\.\.47"):
        cliargs.event_id(raw)


@pytest.mark.parametrize("raw", ["2022-23", "2025-26", "2099-00"])
def test_a_well_formed_season_is_accepted(raw: str) -> None:
    assert cliargs.season(raw) == raw


@pytest.mark.parametrize("raw", ["2025", "25-26", "2025_26", "2025/26", "abcd-ef"])
def test_a_malformed_season_is_refused(raw: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="2025-26"):
        cliargs.season(raw)


@pytest.mark.parametrize("raw", ["2025-27", "2025-25", "2025-30"])
def test_a_season_naming_non_consecutive_years_is_refused(raw: str) -> None:
    """A typo that passes the pattern is the one worth catching: 2025-27 looks
    right and would file a whole ingest under a season that does not exist."""
    with pytest.raises(argparse.ArgumentTypeError, match="consecutive"):
        cliargs.season(raw)


def test_the_parsers_reject_before_any_work_happens() -> None:
    """End to end through argparse: a bad flag exits 2 without importing a
    client, opening a socket or touching the database."""
    from fpl_andres.cli.sweep_managers import build_parser

    with pytest.raises(SystemExit) as caught:
        build_parser().parse_args(["--rate", "0"])

    assert caught.value.code == 2


def test_a_valid_invocation_still_parses() -> None:
    from fpl_andres.cli.sweep_managers import build_parser

    args = build_parser().parse_args(["--rate", "12.5", "--concurrency", "4"])

    assert args.rate == 12.5
    assert args.concurrency == 4
