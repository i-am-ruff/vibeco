"""Tests for DegradedModeManager -- health checking and degraded mode transitions."""

import asyncio

import pytest

from vcompany.supervisor.child_spec import ChildSpec
from vcompany.supervisor.child_spec import ContainerContext
from vcompany.resilience.degraded_mode import DegradedModeManager
from vcompany.supervisor.company_root import CompanyRoot


class TestDegradedModeState:
    """Test state transitions between normal and degraded."""

    @pytest.mark.asyncio
    async def test_initial_state_is_normal(self):
        """Manager starts in normal state."""

        async def healthy():
            return True

        mgr = DegradedModeManager(health_check=healthy)
        assert mgr.state == "normal"
        assert mgr.is_degraded is False

    @pytest.mark.asyncio
    async def test_enter_degraded_after_3_failures(self):
        """3 consecutive failures transitions state from NORMAL to DEGRADED."""

        async def healthy():
            return True

        mgr = DegradedModeManager(health_check=healthy, failure_threshold=3)
        # Simulate 3 consecutive failures
        await mgr._record_result(False)
        await mgr._record_result(False)
        assert mgr.state == "normal"  # Not yet
        await mgr._record_result(False)
        assert mgr.state == "degraded"
        assert mgr.is_degraded is True

    @pytest.mark.asyncio
    async def test_no_premature_degraded(self):
        """2 failures followed by 1 success stays NORMAL."""

        async def healthy():
            return True

        mgr = DegradedModeManager(health_check=healthy, failure_threshold=3)
        await mgr._record_result(False)
        await mgr._record_result(False)
        await mgr._record_result(True)  # Reset
        assert mgr.state == "normal"
        # Even after more failures, counter was reset
        await mgr._record_result(False)
        assert mgr.state == "normal"

    @pytest.mark.asyncio
    async def test_auto_recovery_after_2_successes(self):
        """In DEGRADED state, 2 consecutive successes transitions back to NORMAL."""

        async def healthy():
            return True

        mgr = DegradedModeManager(
            health_check=healthy, failure_threshold=3, recovery_threshold=2
        )
        # Enter degraded
        for _ in range(3):
            await mgr._record_result(False)
        assert mgr.state == "degraded"
        # Recover
        await mgr._record_result(True)
        assert mgr.state == "degraded"  # Not yet
        await mgr._record_result(True)
        assert mgr.state == "normal"

    @pytest.mark.asyncio
    async def test_no_premature_recovery(self):
        """In DEGRADED, 1 success followed by 1 failure stays DEGRADED."""

        async def healthy():
            return True

        mgr = DegradedModeManager(
            health_check=healthy, failure_threshold=3, recovery_threshold=2
        )
        # Enter degraded
        for _ in range(3):
            await mgr._record_result(False)
        assert mgr.state == "degraded"
        # One success, then failure
        await mgr._record_result(True)
        await mgr._record_result(False)
        assert mgr.state == "degraded"

    @pytest.mark.asyncio
    async def test_is_degraded_property(self):
        """is_degraded returns True only in DEGRADED state."""

        async def healthy():
            return True

        mgr = DegradedModeManager(health_check=healthy, failure_threshold=3)
        assert mgr.is_degraded is False
        for _ in range(3):
            await mgr._record_result(False)
        assert mgr.is_degraded is True
        # Recover
        for _ in range(2):
            await mgr._record_result(True)
        assert mgr.is_degraded is False


class TestCallbacks:
    """Test on_degraded and on_recovered callbacks."""

    @pytest.mark.asyncio
    async def test_on_degraded_callback(self):
        """Entering DEGRADED calls on_degraded callback exactly once."""
        called = []

        async def on_degraded():
            called.append("degraded")

        async def healthy():
            return True

        mgr = DegradedModeManager(
            health_check=healthy, failure_threshold=3, on_degraded=on_degraded
        )
        for _ in range(3):
            await mgr._record_result(False)
        assert called == ["degraded"]
        # Further failures should NOT call again (already degraded)
        for _ in range(3):
            await mgr._record_result(False)
        assert called == ["degraded"]

    @pytest.mark.asyncio
    async def test_on_recovered_callback(self):
        """Exiting DEGRADED calls on_recovered callback exactly once."""
        called = []

        async def on_recovered():
            called.append("recovered")

        async def healthy():
            return True

        mgr = DegradedModeManager(
            health_check=healthy,
            failure_threshold=3,
            recovery_threshold=2,
            on_recovered=on_recovered,
        )
        # Enter degraded
        for _ in range(3):
            await mgr._record_result(False)
        assert called == []
        # Recover
        await mgr._record_result(True)
        await mgr._record_result(True)
        assert called == ["recovered"]


class TestHealthCheckFunc:
    """Test that health_check callable is used correctly."""

    @pytest.mark.asyncio
    async def test_check_health_func_uses_injected_callable(self):
        """Uses injected health_check callable (not real API)."""
        results = [True, False, False, False]
        call_count = 0

        async def mock_check():
            nonlocal call_count
            idx = min(call_count, len(results) - 1)
            call_count += 1
            return results[idx]

        mgr = DegradedModeManager(health_check=mock_check, failure_threshold=3)
        # Manually call _record_result via health check
        result = await mock_check()
        await mgr._record_result(result)
        assert mgr.state == "normal"

    @pytest.mark.asyncio
    async def test_health_check_exception_counts_as_unhealthy(self):
        """If health_check raises, it counts as unhealthy."""
        call_count = 0

        async def failing_check():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("API unreachable")

        mgr = DegradedModeManager(
            health_check=failing_check, failure_threshold=3, check_interval=0.01
        )
        await mgr.start()
        # Give loop time to run a few checks
        await asyncio.sleep(0.1)
        await mgr.stop()
        assert mgr.state == "degraded"
        assert call_count >= 3


class TestPeriodicLoop:
    """Test the background health check loop."""

    @pytest.mark.asyncio
    async def test_periodic_loop_runs_at_interval(self):
        """Health check loop runs at configured interval."""
        call_count = 0

        async def mock_check():
            nonlocal call_count
            call_count += 1
            return True

        mgr = DegradedModeManager(
            health_check=mock_check, check_interval=0.01
        )
        await mgr.start()
        await asyncio.sleep(0.1)
        await mgr.stop()
        # Should have been called multiple times
        assert call_count >= 3


class TestOperationalDetection:
    """Test passive operational failure/success recording."""

    @pytest.mark.asyncio
    async def test_record_operational_failure(self):
        """Passive detection: recording failures can trigger degraded mode."""

        async def healthy():
            return True

        mgr = DegradedModeManager(health_check=healthy, failure_threshold=3)
        await mgr.record_operational_failure()
        await mgr.record_operational_failure()
        assert mgr.state == "normal"
        await mgr.record_operational_failure()
        assert mgr.state == "degraded"

    @pytest.mark.asyncio
    async def test_record_operational_success(self):
        """Passive detection: recording successes can trigger recovery."""

        async def healthy():
            return True

        mgr = DegradedModeManager(
            health_check=healthy, failure_threshold=3, recovery_threshold=2
        )
        # Enter degraded
        for _ in range(3):
            await mgr.record_operational_failure()
        assert mgr.state == "degraded"
        await mgr.record_operational_success()
        assert mgr.state == "degraded"
        await mgr.record_operational_success()
        assert mgr.state == "normal"


def _make_spec(child_id: str) -> ChildSpec:
    return ChildSpec(
        child_id=child_id,
        agent_type="test",
        context=ContainerContext(agent_id=child_id, agent_type="test"),
    )


class TestCompanyRootDegradedMode:
    """Integration tests for CompanyRoot with DegradedModeManager."""

    @pytest.mark.asyncio
    async def test_company_root_dispatch_blocked(self, tmp_path):
        """add_project() raises RuntimeError when system is degraded."""

        async def unhealthy():
            return False

        root = CompanyRoot(
            health_check=unhealthy,
            data_dir=tmp_path,
        )
        await root.start()
        try:
            # Manually trigger degraded state via the manager
            assert root._degraded_mode is not None
            for _ in range(3):
                await root._degraded_mode._record_result(False)
            assert root.is_degraded is True

            with pytest.raises(RuntimeError, match="degraded mode"):
                await root.add_project("proj1", [_make_spec("a1")])
        finally:
            await root.stop()

    @pytest.mark.asyncio
    async def test_company_root_dispatch_allowed_normal(self, tmp_path):
        """add_project() works normally when system is not degraded."""

        async def healthy():
            return True

        root = CompanyRoot(
            health_check=healthy,
            data_dir=tmp_path,
        )
        await root.start()
        try:
            assert root.is_degraded is False
            ps = await root.add_project("proj1", [_make_spec("a1")])
            assert ps is not None
            assert "proj1" in root.projects
        finally:
            await root.stop()

    @pytest.mark.asyncio
    async def test_company_root_is_degraded_property(self, tmp_path):
        """is_degraded reflects DegradedModeManager state."""

        async def healthy():
            return True

        root = CompanyRoot(
            health_check=healthy,
            data_dir=tmp_path,
        )
        await root.start()
        try:
            assert root.is_degraded is False
            # Enter degraded
            for _ in range(3):
                await root._degraded_mode._record_result(False)
            assert root.is_degraded is True
            # Recover
            for _ in range(2):
                await root._degraded_mode._record_result(True)
            assert root.is_degraded is False
        finally:
            await root.stop()

    @pytest.mark.asyncio
    async def test_company_root_no_health_check(self, tmp_path):
        """CompanyRoot without health_check has no degraded mode manager."""
        root = CompanyRoot(data_dir=tmp_path)
        assert root._degraded_mode is None
        assert root.is_degraded is False
        await root.start()
        try:
            # add_project should work fine without health check
            ps = await root.add_project("proj1", [_make_spec("a1")])
            assert ps is not None
        finally:
            await root.stop()

    @pytest.mark.asyncio
    async def test_containers_stay_alive(self, tmp_path):
        """Existing containers stay alive when system enters degraded mode."""

        async def healthy():
            return True

        root = CompanyRoot(
            health_check=healthy,
            data_dir=tmp_path,
        )
        await root.start()
        try:
            # Add a project before degraded
            ps = await root.add_project("proj1", [_make_spec("a1")])
            assert ps.state == "running"

            # Enter degraded
            for _ in range(3):
                await root._degraded_mode._record_result(False)
            assert root.is_degraded is True

            # Existing project supervisor is still running
            assert ps.state == "running"
            assert "proj1" in root.projects
        finally:
            await root.stop()

    @pytest.mark.asyncio
    async def test_owner_notified_on_degraded(self, tmp_path):
        """on_degraded callback is called when entering degraded mode."""
        notifications = []

        async def on_degraded():
            notifications.append("degraded")

        async def on_recovered():
            notifications.append("recovered")

        async def healthy():
            return True

        root = CompanyRoot(
            health_check=healthy,
            on_degraded=on_degraded,
            on_recovered=on_recovered,
            data_dir=tmp_path,
        )
        await root.start()
        try:
            # Enter degraded
            for _ in range(3):
                await root._degraded_mode._record_result(False)
            assert notifications == ["degraded"]

            # Recover
            for _ in range(2):
                await root._degraded_mode._record_result(True)
            assert notifications == ["degraded", "recovered"]
        finally:
            await root.stop()
