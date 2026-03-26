"""Sphinx configuration for ThunderGraph user documentation."""

from __future__ import annotations

import sys
from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = DOCS_ROOT.parent.parent

# Autodoc import path for tg_model.
sys.path.insert(0, str(PROJECT_ROOT))

project = "ThunderGraph Model"
author = "ThunderGraph"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

autosummary_generate = True

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}

autodoc_typehints = "description"
autodoc_member_order = "bysource"

# API reference pages under ``api/*.rst`` use reStructuredText on purpose: ``automodule``
# must run with the real Sphinx/docutils state machine. MyST markdown uses a mock state
# whose ``nested_parse`` feeds generated autodoc text back through the Markdown renderer,
# which leaves ``.. py:class::`` / ``.. py:method::`` as literal paragraphs (broken HTML).

napoleon_google_docstring = False
napoleon_numpy_docstring = True

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

templates_path = ["_templates"]
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "IMPLEMENTATION_PLAN.md",
    "README.md",
    "drafts/README.md",
]

html_theme = "furo"
html_theme_options = {
    "navigation_with_keys": True,
    "light_css_variables": {
        "font-stack": "system-ui, -apple-system, 'Segoe UI', sans-serif",
        "font-stack--monospace": "ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
    },
    "dark_css_variables": {
        "font-stack": "system-ui, -apple-system, 'Segoe UI', sans-serif",
        "font-stack--monospace": "ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
    },
}
html_static_path = ["_static"]
html_title = "ThunderGraph Model Docs"

master_doc = "index"
