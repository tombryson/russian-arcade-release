import re

from flask import render_template, request


def is_shell_navigation():
    """HTMX sidebar navigation swaps the main page shell, not inner fragments."""
    return request.headers.get("HX-Target") == "mainContent"


def extract_main_content(html):
    # The target ID is stable; page-specific classes and attribute order are not.
    opening = re.search(
        r'''<(main|div)\b(?=[^>]*\s+id\s*=\s*(["'])mainContent\2)[^>]*>''',
        html,
        re.IGNORECASE,
    )
    if opening is None:
        return html
    start = opening.start()
    tag = opening.group(1)
    depth = 0
    for match in re.finditer(rf"<(/?){tag}\b[^>]*>", html[start:], re.IGNORECASE):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            return html[start : start + match.end()]
    return html


def render_page(template_name, **context):
    html = render_template(template_name, **context)
    if is_shell_navigation():
        return extract_main_content(html)
    return html
