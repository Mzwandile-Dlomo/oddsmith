from oddsmith.odds_model.service import _norm
from oddsmith.providers.merge import _normalize_team
from oddsmith.textnorm import fold_accents


def test_fold_accents_maps_to_base_letters():
    assert fold_accents("Grêmio") == "Gremio"
    assert fold_accents("Atlético Tucuman") == "Atletico Tucuman"
    assert fold_accents("São Paulo") == "Sao Paulo"


def test_fold_accents_leaves_ascii_untouched():
    assert fold_accents("Arsenal") == "Arsenal"


def test_model_lookup_matches_across_accents():
    # The providers send the accented spelling; the history table holds ASCII.
    # Dropping the accent instead of folding it produced "atlticotucuman", which
    # never matched — and silently disabled the model for the club.
    assert _norm("Atlético Tucuman") == _norm("Atletico Tucuman")
    assert _norm("Grêmio") == _norm("Gremio")
    assert _norm("São Paulo") == _norm("Sao Paulo")


def test_fixture_merge_matches_across_accents():
    # Two providers spelling the same club differently must collapse to one key.
    assert _normalize_team("Grêmio FC") == _normalize_team("Gremio FC")
    assert _normalize_team("Atlético-MG") == _normalize_team("Atletico MG")
