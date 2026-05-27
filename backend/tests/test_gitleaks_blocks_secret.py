"""PLT-04 acceptance: gitleaks blocks the synthetic-secret fixture.

This test proves the two XPredict custom rules (`xpredict-admin-token` and
`xpredict-session-signing-key`) fire against the fixture in
``backend/tests/fixtures/synthetic_secrets/.env.fake`` — confirming that
if a real ``ADMIN_TOKEN=…`` or ``SESSION_SIGNING_KEY=…`` is ever committed,
the linter catches it.

It also verifies that the same gitleaks config, applied with its
allowlist active, scans the full repo cleanly (0 findings) — proving the
fixture is correctly allowlisted for the developer-checkin path.

The fixture itself ships in a directory whose path matches the
``tests/.*fixtures.*`` allowlist regex; the test invokes gitleaks WITHOUT
the allowlist (via a temp config) to force the rules to fire.

This is the PLT-04 portion of the Phase 1 ROADMAP Success Criteria #5.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "synthetic_secrets"

GITLEAKS = shutil.which("gitleaks")

_SKIP_REASON = (
    "gitleaks not installed on PATH; install via 'scoop install gitleaks' "
    "(Windows) or 'brew install gitleaks' (macOS) — required for PLT-04 "
    "verification"
)

pytestmark = pytest.mark.skipif(GITLEAKS is None, reason=_SKIP_REASON)


# ---------------------------------------------------------------------------
# Negative test config — same rules, no allowlist. Built dynamically inside
# the test so the fixture isn't allowlisted away.
# ---------------------------------------------------------------------------

_NEGATIVE_CONFIG = """\
title = "XPredict gitleaks config (no allowlist - for negative test)"
[extend]
useDefault = true

[[rules]]
id = "xpredict-session-signing-key"
description = "XPredict session signing key (Phase 2)"
regex = '''SESSION_SIGNING_KEY\\s*=\\s*['\"]?[A-Za-z0-9+/=]{32,}'''
tags = ["secret", "key"]

[[rules]]
id = "xpredict-admin-token"
description = "XPredict admin token (Phase 2)"
regex = '''ADMIN_TOKEN\\s*=\\s*['\"]?[A-Za-z0-9_-]{16,}'''
tags = ["secret", "key"]
"""


def _run_gitleaks(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run gitleaks and return (exit_code, stdout, stderr)."""
    assert GITLEAKS is not None
    proc = subprocess.run(
        [GITLEAKS, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_gitleaks_fires_on_synthetic_fixture(tmp_path: Path) -> None:
    """PLT-04 negative-test: rules detect the fixture's two fake secrets.

    Runs gitleaks against the synthetic-secrets fixture directory using a
    temporary config that omits the allowlist. Asserts both custom rules
    produced exactly one finding each (2 total).
    """
    negative_config = tmp_path / "gitleaks-negative.toml"
    negative_config.write_text(_NEGATIVE_CONFIG, encoding="utf-8")

    report_path = tmp_path / "findings.json"

    exit_code, stdout, stderr = _run_gitleaks(
        [
            "detect",
            f"--config={negative_config}",
            f"--source={FIXTURE_DIR}",
            "--no-banner",
            "--no-git",
            "--report-format=json",
            f"--report-path={report_path}",
        ],
        cwd=REPO_ROOT,
    )

    # Exit code 1 means gitleaks detected at least one finding (WR-07).
    # Exit code 0 means no findings — the rules failed to fire.
    # Exit code 2 means gitleaks itself crashed.
    assert exit_code == 1, (
        f"expected gitleaks to exit 1 (findings detected); got {exit_code}. "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert report_path.exists(), f"gitleaks did not produce a JSON report at {report_path}"

    findings = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(
        findings, list
    ), f"expected JSON array, got {type(findings).__name__}: {findings!r}"
    assert len(findings) == 2, (
        f"expected exactly 2 findings (admin token + session signing key); "
        f"got {len(findings)}: {findings!r}"
    )

    rule_ids = sorted(finding["RuleID"] for finding in findings)
    assert rule_ids == [
        "xpredict-admin-token",
        "xpredict-session-signing-key",
    ], f"unexpected rule IDs: {rule_ids!r}"


def test_gitleaks_clean_scan_of_full_repo(tmp_path: Path) -> None:
    """PLT-04 positive-test: full repo with allowlist active reports 0 findings.

    Runs gitleaks against the entire repo using the committed
    ``.gitleaks.toml`` config (which has the allowlist active). Asserts
    zero findings — the synthetic fixture is allowlisted, no other real
    secrets exist, and the default ruleset catches nothing.
    """
    assert GITLEAKS_CONFIG.exists(), f".gitleaks.toml missing at repo root: {GITLEAKS_CONFIG}"

    report_path = tmp_path / "clean-findings.json"

    _run_gitleaks(
        [
            "detect",
            f"--config={GITLEAKS_CONFIG}",
            f"--source={REPO_ROOT}",
            "--no-banner",
            "--report-format=json",
            f"--report-path={report_path}",
        ],
        cwd=REPO_ROOT,
    )

    assert report_path.exists(), f"gitleaks did not produce a JSON report at {report_path}"

    findings = json.loads(report_path.read_text(encoding="utf-8"))
    # Empty result file may serialize as null/empty list depending on the
    # gitleaks version — both mean "no leaks found".
    if findings is None:
        findings = []
    assert isinstance(
        findings, list
    ), f"expected JSON array or null, got {type(findings).__name__}: {findings!r}"
    assert len(findings) == 0, (
        f"expected 0 findings on the allowlisted full-repo scan; got "
        f"{len(findings)} unexpected leak(s): {findings!r}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-x", "-v"]))
