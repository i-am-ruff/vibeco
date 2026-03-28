---
type: quick
autonomous: true
files_modified:
  - src/vcompany/agent/gsd_agent.py
  - src/vcompany/bot/cogs/plan_review.py
  - tests/test_gsd_agent.py
---

<objective>
Fix PM review gate to support modify/clarify re-entrant loop and extend PM review to all GSD stages.

Currently advance_phase() creates a one-shot Future gate -- when PM says "modify" or "clarify", the Future resolves and the agent continues past the gate. This is wrong: the agent should loop back, re-create the gate, and wait for PM to approve the revised work.

Additionally, dispatch_pm_review() only uses PlanReviewer for the "plan" stage and auto-approves everything else. All stages should get real PM evaluation.

Purpose: Agents must not proceed past a gate until PM explicitly approves. PM must actually review all stage artifacts, not just plans.
Output: Modified gsd_agent.py, plan_review.py, and a focused test for the re-entrant loop.
</objective>

<context>
@src/vcompany/agent/gsd_agent.py
@src/vcompany/bot/cogs/plan_review.py
@src/vcompany/strategist/plan_reviewer.py
@tests/test_gsd_agent.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Make advance_phase() loop until approve</name>
  <files>src/vcompany/agent/gsd_agent.py, tests/test_gsd_agent.py</files>
  <action>
In GsdAgent.advance_phase(), replace the single Future-await-return pattern with a loop:

```python
async def advance_phase(self, phase: str) -> str:
    # ... existing transition + checkpoint + phase_transition callback (unchanged) ...

    # GATE-01: Loop until PM approves (modify/clarify re-enter the gate)
    loop = asyncio.get_running_loop()
    self._review_attempts = 0
    while True:
        self._pending_review = loop.create_future()
        # Post review request via callback (wired by VcoBot.on_ready)
        if self._on_review_request is not None:
            await self._on_review_request(self.context.agent_id, phase)
        try:
            decision = await self._pending_review
        finally:
            self._pending_review = None

        if decision == "approve":
            return decision

        # modify/clarify: agent receives feedback via tmux (handled by
        # _handle_review_response in PlanReviewCog), then we loop back
        # and re-create the gate to wait for next PM decision.
        self._review_attempts += 1
        if self._review_attempts >= self._max_review_attempts:
            logger.warning(
                "Agent %s hit max review attempts (%d) for phase %s, auto-approving",
                self.context.agent_id, self._max_review_attempts, phase,
            )
            return "approve"
        logger.info(
            "Agent %s received '%s' for phase %s (attempt %d/%d), re-entering gate",
            self.context.agent_id, decision, phase,
            self._review_attempts, self._max_review_attempts,
        )
```

Key points:
- The while-True loop re-creates the Future each iteration
- Only "approve" breaks out of the loop
- Max attempts safety valve prevents infinite loops (uses existing _max_review_attempts=3)
- The `finally: self._pending_review = None` cleanup happens each iteration before re-creating
- resolve_review() stays unchanged -- it just resolves whichever Future is currently pending

Add a focused test in tests/test_gsd_agent.py:

```python
class TestReviewGateLoop:
    """advance_phase re-enters gate on modify/clarify until approve."""

    @pytest.mark.asyncio
    async def test_modify_then_approve(self, tmp_path: Path) -> None:
        """Gate blocks after modify, only continues after approve."""
        agent = GsdAgent(context=_ctx(), data_dir=tmp_path)
        decisions = iter(["modify", "approve"])

        async def _staged_review(aid: str, stage: str) -> None:
            agent.resolve_review(next(decisions))

        agent._on_review_request = _staged_review
        await agent.start()
        result = await agent.advance_phase("discuss")
        assert result == "approve"
        assert agent._review_attempts == 1  # one modify before approve
        await agent.stop()

    @pytest.mark.asyncio
    async def test_clarify_then_modify_then_approve(self, tmp_path: Path) -> None:
        """Multiple non-approve decisions loop until approve."""
        agent = GsdAgent(context=_ctx(), data_dir=tmp_path)
        decisions = iter(["clarify", "modify", "approve"])

        async def _staged_review(aid: str, stage: str) -> None:
            agent.resolve_review(next(decisions))

        agent._on_review_request = _staged_review
        await agent.start()
        result = await agent.advance_phase("plan")
        assert result == "approve"
        assert agent._review_attempts == 2
        await agent.stop()

    @pytest.mark.asyncio
    async def test_max_attempts_auto_approves(self, tmp_path: Path) -> None:
        """After max_review_attempts non-approvals, auto-approves."""
        agent = GsdAgent(context=_ctx(), data_dir=tmp_path)
        agent._max_review_attempts = 2

        async def _always_modify(aid: str, stage: str) -> None:
            agent.resolve_review("modify")

        agent._on_review_request = _always_modify
        await agent.start()
        result = await agent.advance_phase("execute")
        assert result == "approve"
        assert agent._review_attempts == 2
        await agent.stop()
```
  </action>
  <verify>
    <automated>cd /home/developer/vcompany && uv run pytest tests/test_gsd_agent.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>advance_phase() loops on modify/clarify, only returns on approve (or max attempts). Three new tests pass covering modify-then-approve, multi-rejection, and max-attempts safety valve.</done>
</task>

<task type="auto">
  <name>Task 2: Extend dispatch_pm_review to all GSD stages</name>
  <files>src/vcompany/bot/cogs/plan_review.py</files>
  <action>
In PlanReviewCog.dispatch_pm_review(), replace the `if stage == "plan"` branch with unified review logic that uses PlanReviewer for ALL stages. The PlanReviewer.review_plan() method already accepts arbitrary content -- "plan" is just the name, it does scope/dependency/duplicate checks on any content with frontmatter.

For non-plan stages (discuss, execute, uat, ship), the artifacts may not have frontmatter, so the scope/dep/dup checks will mostly pass (no files_modified = scope passes, no depends_on = dep passes, etc). This is correct behavior -- the PM still logs the review and posts to Discord.

Replace lines 686-706 (the `if stage == "plan" and self._plan_reviewer:` block and the fallback auto-approve) with:

```python
        # Use PlanReviewer for ALL stages (not just plan)
        if self._plan_reviewer and artifact_content:
            try:
                review = await asyncio.to_thread(
                    self._plan_reviewer.review_plan, agent_id, artifact_content
                )
                if review.confidence.level == "HIGH":
                    response = f"[PM] APPROVED: {review.note or f'{stage} stage approved'}"
                else:
                    response = f"[PM] NEEDS CHANGES: {review.note}"
                self._append_pm_context(
                    f"## {agent_id} {stage} review: {review.note[:200] if review.note else 'approved'}"
                )
                await self._post_throttled(agent_id, channel, response)
                return
            except Exception:
                logger.exception("PlanReviewer failed for %s %s", agent_id, stage)

        # Fallback: auto-approve if no reviewer or no artifacts
        response = f"[PM] APPROVED: {stage} stage looks good for {agent_id}"
        self._append_pm_context(f"## {agent_id} {stage} auto-approved")
        await self._post_throttled(agent_id, channel, response)
```

Also update the docstring for dispatch_pm_review to remove the "auto-approves other stages" wording and the "Phase 15 scope" comment on line 703. Replace with: "Uses PlanReviewer for all stage artifacts. Falls back to auto-approve if no reviewer configured or no artifacts found."

Remove the outdated comment on line 703: `# (Full PMTier integration for non-plan stages is Phase 15 scope)`.
  </action>
  <verify>
    <automated>cd /home/developer/vcompany && uv run pytest tests/test_plan_review_cog.py tests/test_gsd_agent.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>dispatch_pm_review() uses PlanReviewer for all stages (discuss, plan, execute, uat, ship). Non-plan artifacts that lack frontmatter still pass scope/dep/dup checks gracefully. Fallback auto-approve only triggers when no reviewer is configured or no artifacts exist.</done>
</task>

</tasks>

<verification>
1. `uv run pytest tests/test_gsd_agent.py tests/test_plan_review_cog.py -x -q` -- all tests pass
2. `uv run ruff check src/vcompany/agent/gsd_agent.py src/vcompany/bot/cogs/plan_review.py` -- no lint errors
3. Manual trace: advance_phase("plan") -> resolve_review("modify") -> agent stays blocked -> resolve_review("approve") -> agent continues
</verification>

<success_criteria>
- advance_phase() blocks agent after modify/clarify, re-creating the gate Future in a loop
- Only "approve" decision (or max attempts) allows agent to proceed
- dispatch_pm_review() runs PlanReviewer for all 5 GSD stages, not just plan
- Existing tests still pass, new re-entrant loop tests pass
</success_criteria>
