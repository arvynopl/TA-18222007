"""tests/test_feedback_single_survey.py — dedupe verification for the
post-session survey. There must be exactly one survey-rendering helper on
the feedback page."""

import re
from pathlib import Path


def test_renderer_has_single_post_session_survey_helper():
    renderer = Path(__file__).resolve().parent.parent / "modules/feedback/renderer.py"
    src = renderer.read_text(encoding="utf-8")
    # Exactly one definition …
    assert src.count("def _render_post_session_survey(") == 1
    # … and exactly one call site inside render_feedback_page.
    assert src.count("_render_post_session_survey(") == 2  # def + 1 call

    # The feedback page must NOT open a second PostSessionSurvey form.
    app_py = Path(__file__).resolve().parent.parent / "app.py"
    app_src = app_py.read_text(encoding="utf-8")
    assert "post_session_survey_form" not in app_src, (
        "app.py _page_hasil must not render a duplicate PostSessionSurvey form; "
        "renderer.py owns the single survey block."
    )
    assert re.search(r"PostSessionSurvey\s*\(", app_src) is None


def test_comparison_uses_latest_survey():
    comp = Path(__file__).resolve().parent.parent / "modules/analytics/comparison.py"
    src = comp.read_text(encoding="utf-8")
    assert "UserSurvey.submitted_at" in src, (
        "build_stated_vs_revealed must order by submitted_at.desc() to use "
        "the user's latest survey (onboarding or session-level)."
    )
