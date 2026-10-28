"""Pseudo-harmonic action translation (Ganzfried & Sandholm, IJCAI 2013).

An observed bet of ``x`` pot fractions between two abstract sizes ``a < b`` is
read as ``a`` with probability ``((b - x)(1 + a)) / ((b - a)(1 + x))``, else as
``b``. Same mapping as robopoker's ``Lattice::pharmonic`` (MIT), written here
from the paper. Not wired into the V2 agent, whose nearest-log-size reading is
part of every evaluated result; a switch needs its own preregistered test.
"""


def pseudo_harmonic(a: float, b: float, x: float) -> float:
    """Probability of mapping ``x`` to the smaller size ``a``."""
    if not a < b or not a <= x <= b:
        raise ValueError("Need a <= x <= b with a < b")
    return ((b - x) * (1 + a)) / ((b - a) * (1 + x))


def translate(x: float, sizes: list[float], rng=None) -> float:
    """The abstract size for ``x``: sampled with ``rng``, else the more likely one."""
    sizes = sorted(sizes)
    if x <= sizes[0]:
        return sizes[0]
    if x >= sizes[-1]:
        return sizes[-1]
    b = next(s for s in sizes if s >= x)
    a = sizes[sizes.index(b) - 1]
    if x == b:
        return b
    p = pseudo_harmonic(a, b, x)
    if rng is None:
        return a if p >= 0.5 else b
    return a if rng.random() < p else b
