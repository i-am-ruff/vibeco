"""Jinja2 template environment and rendering utilities.

Uses StrictUndefined to catch missing variables at render time rather than
silently inserting empty strings (per D-09, Pitfall 6).
"""

import jinja2
from pathlib import Path


def create_template_env() -> jinja2.Environment:
    """Create Jinja2 environment with strict undefined checking (per D-09, Pitfall 6)."""
    template_dir = Path(__file__).parent.parent / "templates"
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(template_name: str, **kwargs: object) -> str:
    """Render a Jinja2 template by name with given variables."""
    env = create_template_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)
