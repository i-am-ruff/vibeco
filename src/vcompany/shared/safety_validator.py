"""Safety table validator for PLAN.md files.

Pure stateless utility -- validates that plans include an Interaction Safety
section with the required 6-column markdown table per SAFE-01/SAFE-02.

Moved from vcompany.monitor.safety_validator to vcompany.shared during Phase 22
to keep bot cog imports within allowed namespaces.
"""

import re


REQUIRED_COLUMNS = [
    "Agent/Component",
    "Circumstance",
    "Action",
    "Concurrent With",
    "Safe?",
    "Mitigation",
]


def validate_safety_table(plan_content: str) -> tuple[bool, str]:
    """Check PLAN.md content for Interaction Safety section with required columns.

    Args:
        plan_content: Full text content of a PLAN.md file.

    Returns:
        Tuple of (is_valid, reason_message).
    """
    # Check for ## Interaction Safety heading (must be h2, not h3+)
    match = re.search(r"^##\s+Interaction Safety\s*$", plan_content, re.MULTILINE)
    if not match:
        return False, "Missing '## Interaction Safety' section"

    # Extract section content after the heading
    section_start = match.end()
    # Find next h2 or end of file
    next_h2 = re.search(r"^##\s+", plan_content[section_start:], re.MULTILINE)
    if next_h2:
        section = plan_content[section_start : section_start + next_h2.start()]
    else:
        section = plan_content[section_start:]

    # Find lines that look like table rows (start and end with |)
    table_rows = re.findall(r"^\|.+\|$", section, re.MULTILINE)
    if not table_rows:
        return False, "No table found in Interaction Safety section"

    # First table row should be the header
    header_row = table_rows[0].lower()
    missing_cols = [col for col in REQUIRED_COLUMNS if col.lower() not in header_row]

    if missing_cols:
        return False, f"Safety table missing required columns: {', '.join(missing_cols)}"

    # Filter out separator rows (contain only |, -, :, spaces)
    data_rows = [
        row for row in table_rows[1:] if not re.match(r"^\|[\s\-:|]+\|$", row)
    ]

    if len(data_rows) < 1:
        return False, "Safety table has no data rows"

    return True, "Safety table validated"
