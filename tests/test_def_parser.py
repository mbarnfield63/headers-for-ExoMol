"""Assert-based self-check. Run directly: python tests/test_def_parser.py
(also picked up by pytest if installed — no framework required either way).

Fixtures are hand-built and synthetic, not real ExoMol files (none
downloaded yet — see DESIGN.md "Testing"). They exist to prove the
mechanism, especially label-driven drift tolerance (Q17): the fixture
.def deliberately includes one field ("Predissociation availability")
that no keyword pattern recognizes, to check it's captured rather than
breaking the parse.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exomol_headers.def_parser import Schema, parse_def
from exomol_headers.io_utils import sniff_column_count

FIXTURES = Path(__file__).parent / "fixtures"


def test_flags_and_quanta():
    schema = parse_def(FIXTURES / "synthetic__test.def")
    assert schema.flags == {"lifetime": True, "lande": False, "uncertainty": False}
    assert [c.name for c in schema.columns[4:]] == ["tau", "v", "parity"]


def test_unrecognized_field_kept_not_dropped():
    schema = parse_def(FIXTURES / "synthetic__test.def")
    matched = [v for k, v in schema.extra_metadata.items()
               if "predissociation" in k.lower()]
    assert matched == ["0"], "unrecognized .def line should survive as metadata, not vanish"


def test_states_columns_order():
    schema = parse_def(FIXTURES / "synthetic__test.def")
    names = [c.name for c in schema.states_columns()]
    assert names == ["i", "E", "g_tot", "J", "tau", "v", "parity"]


def test_column_count_matches_real_file():
    schema = parse_def(FIXTURES / "synthetic__test.def")
    columns = schema.states_columns()
    actual = sniff_column_count(FIXTURES / "synthetic__test.states")
    assert actual == len(columns), (
        "fixture drifted out of sync with the .def — fix the fixture, "
        "this is exactly the mismatch case cli.py warns about at runtime"
    )


def test_trans_sniffed_as_4_columns():
    assert sniff_column_count(FIXTURES / "synthetic__test.trans") == 4


def test_render_a_is_bare_names():
    schema = parse_def(FIXTURES / "synthetic__test.def")
    assert Schema.render_a(schema.states_columns()) == "i,E,g_tot,J,tau,v,parity"


def test_render_c_includes_units_and_description():
    schema = parse_def(FIXTURES / "synthetic__test.def")
    rendered = Schema.render_c(schema.states_columns())
    assert "[cm-1]" in rendered
    assert "radiative lifetime" in rendered


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
