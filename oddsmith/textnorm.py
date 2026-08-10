"""Unicode folding for team-name matching.

Odds providers and our historical table spell the same club differently: the
providers send "Atlético Tucuman" and "Grêmio", the history holds "Atletico
Tucuman" and "Gremio". Any normaliser that simply drops non-ASCII characters
turns the accented letter into nothing at all — "atlticotucuman" — which will
never match "atleticotucuman", so the model silently declines to price the
fixture.

Folding decomposes each character and discards the combining marks, mapping the
accented letter onto its base letter instead of deleting it.
"""

from __future__ import annotations

import unicodedata


def fold_accents(text: str) -> str:
    """Map accented characters to their ASCII base ('Grêmio' -> 'Gremio')."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
