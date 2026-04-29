"""tests/test_nav_labels.py — v6 top-nav contract."""

from modules.utils.ui_helpers import NAV_ITEMS


def test_nav_has_five_entries():
    # v6 (Phase 4): added "Feedback Penguji" UAT instrumentation page.
    assert len(NAV_ITEMS) == 5


def test_nav_labels_match_spec():
    labels = [label for label, _ in NAV_ITEMS]
    assert labels == [
        "Beranda",
        "Simulasi Investasi",
        "Hasil Analisis & Umpan Balik",
        "Profil Kognitif Saya",
        "Feedback Penguji",
    ]


def test_nav_keys_are_unique():
    keys = [key for _, key in NAV_ITEMS]
    assert len(set(keys)) == len(keys)
