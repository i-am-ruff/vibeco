"""Tests for pre-flight result interpretation and monitor strategy determination.

Unit tests only -- no live Claude Code invocations. Live tests would require
a real API key and are marked with @pytest.mark.slow in the implementation.
"""

import json
from datetime import datetime, timezone

import pytest

from vcompany.orchestrator.preflight import (
    MonitorStrategy,
    PreflightResult,
    PreflightSuite,
    determine_monitor_strategy,
)


# ── PreflightResult tests ───────────────────────────────────────────────


class TestPreflightResult:
    def test_basic_fields(self):
        r = PreflightResult(
            test_name="stream_json_heartbeat",
            passed=True,
            details="Received 5 JSON events",
            duration_seconds=12.3,
        )
        assert r.test_name == "stream_json_heartbeat"
        assert r.passed is True
        assert r.inconclusive is False  # default
        assert r.details == "Received 5 JSON events"
        assert r.duration_seconds == 12.3

    def test_inconclusive_field(self):
        r = PreflightResult(
            test_name="stream_json_heartbeat",
            passed=False,
            inconclusive=True,
            details="Subprocess error",
            duration_seconds=5.0,
        )
        assert r.inconclusive is True
        assert r.passed is False

    def test_json_round_trip(self):
        r = PreflightResult(
            test_name="max_turns_exit",
            passed=True,
            inconclusive=False,
            details="Exit code 1",
            duration_seconds=45.2,
        )
        data = r.model_dump_json()
        restored = PreflightResult.model_validate_json(data)
        assert restored == r


# ── MonitorStrategy tests ────────────────────────────────────────────────


class TestMonitorStrategy:
    def test_stream_json_value(self):
        assert MonitorStrategy.STREAM_JSON == "stream_json"

    def test_git_commit_fallback_value(self):
        assert MonitorStrategy.GIT_COMMIT_FALLBACK == "git_commit_fallback"


# ── determine_monitor_strategy tests ─────────────────────────────────────


class TestDetermineMonitorStrategy:
    def _make_result(self, name: str, passed: bool, inconclusive: bool = False) -> PreflightResult:
        return PreflightResult(
            test_name=name,
            passed=passed,
            inconclusive=inconclusive,
            details="",
            duration_seconds=1.0,
        )

    def test_stream_json_passed_returns_stream_json(self):
        results = [
            self._make_result("stream_json_heartbeat", passed=True),
            self._make_result("permission_hang", passed=True),
            self._make_result("max_turns_exit", passed=True),
            self._make_result("resume_recovery", passed=True),
        ]
        assert determine_monitor_strategy(results) == MonitorStrategy.STREAM_JSON

    def test_stream_json_failed_returns_fallback(self):
        results = [
            self._make_result("stream_json_heartbeat", passed=False),
            self._make_result("permission_hang", passed=True),
            self._make_result("max_turns_exit", passed=True),
            self._make_result("resume_recovery", passed=True),
        ]
        assert determine_monitor_strategy(results) == MonitorStrategy.GIT_COMMIT_FALLBACK

    def test_stream_json_inconclusive_returns_fallback(self):
        results = [
            self._make_result("stream_json_heartbeat", passed=False, inconclusive=True),
            self._make_result("permission_hang", passed=True),
            self._make_result("max_turns_exit", passed=True),
            self._make_result("resume_recovery", passed=True),
        ]
        assert determine_monitor_strategy(results) == MonitorStrategy.GIT_COMMIT_FALLBACK


# ── PreflightSuite tests ────────────────────────────────────────────────


class TestPreflightSuite:
    def _make_suite(self, all_passed: bool = True) -> PreflightSuite:
        results = [
            PreflightResult(
                test_name="stream_json_heartbeat",
                passed=all_passed,
                details="ok",
                duration_seconds=10.0,
            ),
            PreflightResult(
                test_name="permission_hang",
                passed=True,
                details="exits normally",
                duration_seconds=5.0,
            ),
            PreflightResult(
                test_name="max_turns_exit",
                passed=True,
                details="exit code 1",
                duration_seconds=30.0,
            ),
            PreflightResult(
                test_name="resume_recovery",
                passed=True,
                details="session continued",
                duration_seconds=60.0,
            ),
        ]
        strategy = (
            MonitorStrategy.STREAM_JSON
            if all_passed
            else MonitorStrategy.GIT_COMMIT_FALLBACK
        )
        return PreflightSuite(
            results=results,
            strategy=strategy,
            run_at=datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc),
            claude_version="2.1.81",
        )

    def test_to_json_valid(self):
        suite = self._make_suite()
        json_str = suite.model_dump_json()
        data = json.loads(json_str)
        assert len(data["results"]) == 4
        assert data["strategy"] == "stream_json"
        assert data["claude_version"] == "2.1.81"

    def test_from_json_round_trip(self):
        suite = self._make_suite()
        json_str = suite.model_dump_json()
        restored = PreflightSuite.model_validate_json(json_str)
        assert restored.strategy == suite.strategy
        assert len(restored.results) == 4
        assert restored.run_at == suite.run_at
        assert restored.claude_version == suite.claude_version
        for orig, rest in zip(suite.results, restored.results):
            assert orig.test_name == rest.test_name
            assert orig.passed == rest.passed

    def test_summary_multiline(self):
        suite = self._make_suite()
        summary = suite.summary()
        assert isinstance(summary, str)
        assert "\n" in summary
        # Each test name should appear in the summary
        assert "stream_json_heartbeat" in summary
        assert "permission_hang" in summary
        assert "max_turns_exit" in summary
        assert "resume_recovery" in summary

    def test_summary_shows_pass_fail(self):
        suite = self._make_suite(all_passed=False)
        summary = suite.summary()
        assert "FAIL" in summary or "fail" in summary.lower()
        assert "PASS" in summary or "pass" in summary.lower()

    def test_all_passed_true(self):
        suite = self._make_suite(all_passed=True)
        assert suite.all_passed is True

    def test_all_passed_false(self):
        suite = self._make_suite(all_passed=False)
        assert suite.all_passed is False

    def test_summary_shows_inconclusive(self):
        results = [
            PreflightResult(
                test_name="stream_json_heartbeat",
                passed=False,
                inconclusive=True,
                details="Subprocess error",
                duration_seconds=5.0,
            ),
            PreflightResult(
                test_name="permission_hang",
                passed=True,
                details="ok",
                duration_seconds=5.0,
            ),
            PreflightResult(
                test_name="max_turns_exit",
                passed=True,
                details="ok",
                duration_seconds=5.0,
            ),
            PreflightResult(
                test_name="resume_recovery",
                passed=True,
                details="ok",
                duration_seconds=5.0,
            ),
        ]
        suite = PreflightSuite(
            results=results,
            strategy=MonitorStrategy.GIT_COMMIT_FALLBACK,
            run_at=datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc),
        )
        summary = suite.summary()
        assert "INCONCLUSIVE" in summary or "inconclusive" in summary.lower()
