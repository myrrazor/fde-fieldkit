from __future__ import annotations

import jinja2


def jinja_env() -> jinja2.Environment:
    """Build the package-backed, HTML-escaping report environment."""

    return jinja2.Environment(
        loader=jinja2.PackageLoader("fieldkit.core"),
        autoescape=jinja2.select_autoescape(("html", "xml")),
    )


def render_page(template_name: str, **ctx: object) -> str:
    """Render a packaged report template with the supplied context."""

    return jinja_env().get_template(template_name).render(**ctx)
