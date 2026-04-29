# CLAUDE.md — Working Notes for the CDT Bias Detection System

This file collects project rules and operational notes used by automated
assistants and contributors. The canonical project README is `README.md`.

## Project Rules

- Tech stack: Streamlit, SQLAlchemy, pandas, Plotly, pytest. Add new top-level
  dependencies only after they are added to `requirements.txt`.
- All UI text in **Bahasa Indonesia** (EYD V).
- Always use `datetime.now(timezone.utc)` — never `datetime.utcnow()`.
- Always wrap DB work in `with get_session() as sess:` — never hold sessions
  across Streamlit reruns.
- Use `logger = logging.getLogger(__name__)` — never `print()` in app code.
- Do not add new DB tables, change bias formulas, or restructure folders
  without an explicit task request.
- Tests use the in-memory SQLite fixtures from `tests/conftest.py`. Never
  import Streamlit in tests.

## Researcher Access

Hidden researcher view at `http://localhost:8501/?view=researcher`.

Enable with:

```bash
export CDT_RESEARCHER_PASSWORD="<your-password>"
streamlit run app.py
```

Provides cohort summary, per-user table, bias distributions, CDT longitudinal
trajectory, survey-vs-observed validation scatter, ML model performance, and
bulk CSV exports. Read-only — no DB writes.

The route is wired in `app.py:main()` early-return (before the standard top
nav) so UAT participants never see it through normal navigation. The page
itself lives at `pages/researcher.py`; cohort-level data helpers live at
`modules/utils/research_export.py` and are unit-tested in
`tests/test_research_export.py`.

When `CDT_RESEARCHER_PASSWORD` is unset the URL renders an inactive-mode
notice and stops; when set, a password form gates access via the
`researcher_authed` session flag.
