"""Extracting candidate manager ids from a saved page rather than a pasted list."""

from __future__ import annotations

from fpl_andres.cohorts.veterans import extract_entry_ids

PAGE = """
<html><body>
  <a href="https://www.reddit.com/r/FantasyPL/team/999999">unrelated link</a>
  <table><tr>
    <td><a href="https://fantasy.premierleague.com/entry/3190/history">Ben</a></td>
  </tr><tr>
    <td><a href="https://fantasy.premierleague.com/entry/7714/history">Graeme</a></td>
  </tr></table>
  <script>var teamId = "team/12345";</script>
</body></html>
"""


def test_a_saved_page_reads_only_manager_history_links() -> None:
    # The stray team/ links must not be swept up as managers.
    assert extract_entry_ids(PAGE) == (3190, 7714)


def test_a_pasted_list_still_accepts_urls_and_bare_numbers() -> None:
    pasted = """
    https://fantasy.premierleague.com/entry/555/event/1
    12345
    """

    assert extract_entry_ids(pasted) == (555, 12345)


def test_duplicates_are_dropped_and_order_preserved() -> None:
    page = PAGE + '<a href="https://fantasy.premierleague.com/entry/3190/history">again</a>'

    assert extract_entry_ids(page) == (3190, 7714)


def test_the_limit_is_respected() -> None:
    assert extract_entry_ids(PAGE, limit=1) == (3190,)


def test_a_page_without_manager_links_finds_nothing_rather_than_guessing() -> None:
    assert extract_entry_ids("<html><body>no managers here</body></html>") == ()
