"""AI-assisted merge conflict resolution via PMTier.

Implements D-04/D-05: only invoked for overlapping-line conflicts.
Non-overlapping changes auto-merge via git (D-05).

Per Pitfall 6: sends only conflict hunks + surrounding context to PM,
not full file contents.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vcompany.strategist.pm import PMTier

logger = logging.getLogger("vcompany.integration.conflict_resolver")

# Number of context lines to include before/after each conflict hunk.
CONTEXT_LINES = 10


class ConflictResolver:
    """AI-assisted merge conflict resolution via PMTier per D-04/D-05.

    Only invoked for overlapping-line conflicts. Non-overlapping changes
    auto-merge via git (D-05).
    """

    def __init__(self, pm: PMTier | None = None) -> None:
        self._pm = pm

    async def resolve(self, conflict_file: Path, cwd: Path) -> str | None:
        """Attempt to resolve a single file's conflicts using PM tier.

        Returns resolved file content string, or None if PM cannot resolve
        (low confidence or no PM configured). Caller should escalate to Discord.

        Per Pitfall 6: only sends conflict hunks + 10-20 lines context, not full file.
        """
        if self._pm is None:
            return None

        hunks = self._extract_conflict_hunks(conflict_file, cwd)
        if not hunks:
            return None

        # Ask PM to resolve each hunk
        for hunk in hunks:
            prompt = (
                "Resolve this merge conflict. Return ONLY the resolved code, "
                "no explanations or markers. If you cannot confidently resolve it, "
                "respond with exactly 'unsure'.\n\n"
                f"Conflicting section:\n```\n{hunk}\n```"
            )

            try:
                # Use _answer_directly to get a raw answer without confidence scoring
                context_docs: dict[str, str] = {}
                response = await self._pm._answer_directly(prompt, context_docs)
            except Exception:
                logger.exception("PM failed to resolve conflict hunk")
                return None

            # Check if PM indicated low confidence
            response_lower = response.lower().strip()
            if any(
                keyword in response_lower
                for keyword in ("unsure", "escalate", "cannot resolve", "not confident")
            ):
                return None

        # If we get here, PM resolved all hunks. Reconstruct the file.
        # For single-hunk case, replace the conflict block with PM's response.
        file_content = conflict_file.read_text()
        resolved = self._apply_resolution(file_content, response)
        return resolved

    def _extract_conflict_hunks(self, conflict_file: Path, cwd: Path) -> list[str]:
        """Extract conflict markers with surrounding context from a file.

        Looks for <<<<<<< ... ======= ... >>>>>>> blocks.
        Includes CONTEXT_LINES lines before and after each block for context.
        """
        try:
            content = conflict_file.read_text()
        except OSError:
            logger.error("Cannot read conflict file: %s", conflict_file)
            return []

        lines = content.splitlines()
        hunks: list[str] = []

        i = 0
        while i < len(lines):
            if lines[i].startswith("<<<<<<<"):
                # Found start of conflict
                start = i
                # Find end marker
                end = start + 1
                while end < len(lines) and not lines[end].startswith(">>>>>>>"):
                    end += 1

                if end >= len(lines):
                    # Malformed conflict (no closing marker)
                    break

                # Include context lines before and after
                ctx_start = max(0, start - CONTEXT_LINES)
                ctx_end = min(len(lines), end + 1 + CONTEXT_LINES)

                hunk_lines = lines[ctx_start:ctx_end]
                hunks.append("\n".join(hunk_lines))
                i = end + 1
            else:
                i += 1

        return hunks

    def _apply_resolution(self, file_content: str, resolved_hunk: str) -> str:
        """Replace the first conflict block in file_content with resolved_hunk."""
        # Match the entire conflict block: <<<<<<< ... ======= ... >>>>>>>
        pattern = re.compile(
            r"<<<<<<<[^\n]*\n.*?\n>>>>>>>[^\n]*",
            re.DOTALL,
        )
        result = pattern.sub(resolved_hunk.strip(), file_content, count=1)
        return result

    async def resolve_all(
        self, conflict_files: list[str], cwd: Path
    ) -> dict[str, str | None]:
        """Try to resolve all conflicting files.

        Returns {filename: resolved_content_or_None}.
        """
        results: dict[str, str | None] = {}
        for filename in conflict_files:
            file_path = cwd / filename
            if file_path.exists():
                results[filename] = await self.resolve(file_path, cwd)
            else:
                results[filename] = None
        return results
