"""Assert-based self-check. Run directly: python tests/test_def_parser.py
(also picked up by pytest if installed — no framework required either way).

Only `.def.json` is supported (the ExoMol database has fully migrated),
so these tests run against the real downloaded fixtures in `./data`
(gitignored — see DESIGN.md "Testing") and skip if that data isn't
present.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exomol_headers.def_parser import parse_def
from exomol_headers.io_utils import sniff_column_count

DATA = Path(__file__).resolve().parents[1] / "data"
_have_real_data = (DATA / "CO" / "12C-16O__4thplus.def.json").exists()


def test_json_def_detected_and_parsed():
    if not _have_real_data:
        print("skip test_json_def_detected_and_parsed (no ./data)")
        return
    schema = parse_def(DATA / "CO" / "12C-16O__4thplus.def.json")
    names = [c.name for c in schema.columns]
    assert names[:4] == ["ID", "E", "gtot", "J"], names
    assert "unc" in names and "tau" in names
    assert schema.flags == {"uncertainty": True, "lifetime": True, "lande": False}


def test_json_column_count_matches_real_states_file():
    if not _have_real_data:
        print("skip test_json_column_count_matches_real_states_file (no ./data)")
        return
    schema = parse_def(DATA / "CO" / "12C-16O__4thplus.def.json")
    actual = sniff_column_count(DATA / "CO" / "12C-16O__4thplus.states.bz2")
    assert actual == len(schema.columns), (actual, len(schema.columns))


def test_json_triatomic_has_more_quanta_than_diatomic():
    if not _have_real_data:
        print("skip test_json_triatomic_has_more_quanta_than_diatomic (no ./data)")
        return
    co = parse_def(DATA / "CO" / "12C-16O__4thplus.def.json")
    h2s = parse_def(DATA / "H2S" / "1H2-32S__AYT2.def.json")
    assert len(h2s.columns) != len(co.columns)
    h2s_actual = sniff_column_count(DATA / "H2S" / "1H2-32S__AYT2.states.bz2")
    assert h2s_actual == len(h2s.columns), (h2s_actual, len(h2s.columns))


def run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    run_all()
