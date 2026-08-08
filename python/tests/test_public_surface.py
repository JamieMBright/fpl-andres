"""What this deployment tells the outside world, on purpose.

Small surfaces, each of which was either a
decision nobody had written down or a claim nobody had checked.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY = REPO_ROOT / "SECURITY.md"
HEALTH = REPO_ROOT / "api" / "health.ts"
PROXY = REPO_ROOT / "api" / "_lib" / "fpl-proxy.ts"
ADAPTER = REPO_ROOT / "python" / "fpl_andres" / "adapters" / "fpl.py"


def _without_comments(source: str) -> str:
    """Strip block and line comments, so prose about a bug is not read as one."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


class TestHealthEndpoint:
    """The commit SHA is public because the repository is."""

    def test_the_reasoning_is_written_down_where_the_code_is(self) -> None:
        source = HEALTH.read_text(encoding="utf-8")
        assert "public" in source
        assert "private" in source, "the endpoint must name the premise that would make it wrong"

    def test_it_rests_on_the_repository_being_public(self) -> None:
        # The premise, asserted so the decision fails rather than rots if the
        # repository ever becomes private.
        security = SECURITY.read_text(encoding="utf-8")
        assert "This is a public repository" in security
        assert "/api/health" in security

    def test_it_exposes_nothing_beyond_the_revision_and_a_liveness_flag(self) -> None:
        # The bound that matters. An endpoint that grows a dependency list or
        # an environment dump is a different endpoint.
        source = HEALTH.read_text(encoding="utf-8")
        payload = re.search(r"\.json\((\{.*?\})\);", source, re.DOTALL)
        assert payload is not None
        keys = set(re.findall(r"^\s*(\w+):", payload.group(1), re.MULTILINE))
        assert keys == {"status", "service", "revision"}

    def test_it_names_no_environment_variable_but_the_two_it_reads(self) -> None:
        source = HEALTH.read_text(encoding="utf-8")
        read = set(re.findall(r"process\.env\.(\w+)", source))
        assert read == {"VERCEL_GIT_COMMIT_SHA", "VERCEL"}

    def test_it_is_never_cached(self) -> None:
        # A cached liveness answer is a liveness answer about the past.
        assert '"Cache-Control", "no-store"' in HEALTH.read_text(encoding="utf-8")


class TestUserAgent:
    """#82: a contact string, not a fingerprint."""

    def _agent(self, path: Path) -> str:
        match = re.search(r'"(FPLAndres/[^"]+)"', path.read_text(encoding="utf-8"))
        assert match is not None, f"{path.name} declares no user agent"
        return match.group(1)

    def test_both_clients_send_the_same_string(self) -> None:
        # They speak to the same upstream. Two spellings would look like two
        # projects, and one of them would eventually be blocked alone.
        assert self._agent(PROXY) == self._agent(ADAPTER)

    def test_it_carries_no_patch_version(self) -> None:
        # A patch-level version changes with each deploy, so an upstream log
        # can distinguish one build of this project from another and, over
        # time, watch it.
        agent = self._agent(PROXY)
        assert re.match(r"^FPLAndres/\d+\.\d+ ", agent), agent
        assert not re.match(r"^FPLAndres/\d+\.\d+\.\d+", agent), agent

    def test_it_carries_a_contact_url(self) -> None:
        # The part that actually matters: how the Premier League would reach
        # somebody if this client were doing something it should not.
        assert "(+https://github.com/" in self._agent(PROXY)


class TestResponseAssembly:
    """#94: the copy that was not needed."""

    def test_the_bounded_body_is_returned_without_being_copied(self) -> None:
        # readBoundedBody allocates exactly `total` bytes and fills them, so
        # the view covers its whole buffer. The copy duplicated up to eight
        # megabytes of bootstrap for no reason.
        source = PROXY.read_text(encoding="utf-8")
        assert "new ArrayBuffer(body.byteLength)" not in source
        assert "new Response(outcome.body, {" in source

    def test_the_size_bound_is_still_enforced(self) -> None:
        # Removing the copy must not remove the reason it looked necessary.
        source = PROXY.read_text(encoding="utf-8")
        assert "readBoundedBody" in source
        assert "oversize" in source


class TestDebugDetail:
    """#95, already resolved, and asserted so it stays that way."""

    def test_no_handler_puts_exception_text_on_a_response_header(self) -> None:
        # The item asked for truncation to be indicated when debug detail is
        # clipped at 300 characters. There is no such clip any more: the header
        # was removed entirely, and the client gets an opaque id instead.
        # Indicating truncation would have been a smaller fix to a larger
        # problem.
        #
        # Comments are stripped first, because `request-log.ts` documents the
        # removal by name and a plain substring search reads that as the bug.
        for path in (REPO_ROOT / "api").rglob("*.ts"):
            source = _without_comments(path.read_text(encoding="utf-8"))
            assert "x-fpl-andres-debug" not in source, path.name
            assert "slice(0, 300)" not in source, path.name

    def test_the_opaque_id_is_what_reaches_the_client(self) -> None:
        log = (REPO_ROOT / "api" / "_lib" / "request-log.ts").read_text(encoding="utf-8")
        assert "x-fpl-andres-request-id" in log
        assert "randomUUID" in log
