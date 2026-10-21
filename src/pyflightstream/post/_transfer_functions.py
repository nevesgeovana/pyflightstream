"""Bessel functions and the unsteady-aerodynamics transfer functions of Theodorsen and Sears.

The functions the quasi-steady corrections apply: ``J`` and ``Y`` of order 0 and 1 by
a decimal power series (small argument) or Hankel's asymptotic expansion (large
argument), and the two lift-deficiency functions built from them. They are pure
numerics with no knowledge of a table or a run, split out of ``post.corrections``,
which re-exports the four public names.
"""

from __future__ import annotations

import math
from decimal import ROUND_FLOOR, Decimal, localcontext

from pyflightstream._errors import ProductError

__all__ = ["bessel_j", "bessel_y", "sears", "theodorsen"]


#: pi and Euler's constant to 100 digits, for the decimal series.
_PI = Decimal(
    "3.141592653589793238462643383279502884197169399375105820974944592307816406286208998628034825342117068"
)
_GAMMA = Decimal(
    "0.5772156649015328606065120900824024310421593359399235988057672348848677267776646709369470632917467495"
)
#: Above this argument the functions are Hankel's asymptotic expansions.
_ASYMPTOTIC_FROM = 30.0
#: Above this argument the phase of the expansion cannot be held to the digits of
#: the constant of pi that is kept, and the functions are refused.
_PHASE_LIMIT = 1e40


def _phase(order: int, x: float) -> float:
    """Return ``x - (n / 2 + 1/4) pi`` reduced to one turn, summed in decimal arithmetic.

    In floats, ``x`` swallows the constant once its spacing passes it, so the phases
    of J0 and J1 coincide and the Theodorsen ratio is a wrong finite number.
    """
    with localcontext() as context:
        context.prec = 160
        shifted = Decimal(x) - (Decimal(order) / 2 + Decimal("0.25")) * _PI
        turns = (shifted / (2 * _PI)).to_integral_value(rounding=ROUND_FLOOR)
        return float(shifted - turns * 2 * _PI)


def _series(order: int, x: float) -> tuple[float, float]:
    """``(J_n(x), Y_n(x))`` for n in (0, 1) and x > 0, by the power series.

    Abramowitz and Stegun 9.1.10 and 9.1.11, summed in decimal arithmetic
    with the precision raised by the digits the alternating terms cancel
    (about ``0.4343 x``), so the float returned is correct to its last bit
    or so.
    """
    digits = 40 + int(0.4343 * x) + 5
    with localcontext() as context:
        context.prec = digits
        big = Decimal(x)
        half = big / 2
        quarter = half * half
        tiny = Decimal(10) ** (-(digits - 8))
        # The k = 0 term of the sum, 1 / (0! n!), which is 1 for n in (0, 1).
        term = Decimal(1)
        harmonic_k = Decimal(0)
        harmonic_kn = Decimal(0) if order == 0 else Decimal(1)
        sum_j = Decimal(0)
        sum_y = Decimal(0)
        k = 0
        while True:
            sum_j += term
            sum_y += (2 * -_GAMMA + harmonic_k + harmonic_kn) * term
            k += 1
            term = term * (-quarter) / (k * (k + order))
            harmonic_k += Decimal(1) / k
            harmonic_kn += Decimal(1) / (k + order)
            if k > x and abs(term) * (1 + abs(harmonic_kn) + abs(harmonic_k)) < tiny:
                break
        power = half if order == 1 else Decimal(1)
        bessel_first = power * sum_j
        logarithm = half.ln()
        second = 2 / _PI * logarithm * bessel_first - power / _PI * sum_y
        if order == 1:
            second -= 1 / (_PI * half)
        return float(bessel_first), float(second)


def _asymptotic(order: int, x: float) -> tuple[float, float]:
    """``(J_n(x), Y_n(x))`` by Hankel's asymptotic expansion (A and S 9.2.5 to 9.2.10)."""
    mu = 4.0 * order * order
    p = q = 0.0
    term = 1.0
    k = 0
    while True:
        if k % 2 == 0:
            p += term if (k // 2) % 2 == 0 else -term
        else:
            q += term if ((k - 1) // 2) % 2 == 0 else -term
        following = term * (mu - (2 * k + 1) ** 2) / ((k + 1) * 8.0 * x)
        k += 1
        if abs(following) < 1e-18 or abs(following) >= abs(term):
            break
        term = following
    chi = _phase(order, x)
    scale = math.sqrt(2.0 / (math.pi * x))
    return (
        scale * (p * math.cos(chi) - q * math.sin(chi)),
        scale * (p * math.sin(chi) + q * math.cos(chi)),
    )


def _bessel(order: int, x: float) -> tuple[float, float]:
    if order not in (0, 1):
        raise ProductError(f"only the orders 0 and 1 are implemented; asked {order}")
    if not math.isfinite(x) or x <= 0.0:
        raise ProductError(f"the argument must be a positive finite number; it is {x!r}")
    if x > _PHASE_LIMIT:
        raise ProductError(
            f"the argument {x!r} is beyond {_PHASE_LIMIT:g}, where the phase of the "
            "functions cannot be held to the constant of pi this module keeps"
        )
    return _series(order, x) if x <= _ASYMPTOTIC_FROM else _asymptotic(order, x)


def bessel_j(order: int, x: float) -> float:
    """Return the Bessel function of the first kind ``J_n(x)``, n in (0, 1), x > 0.

    Parameters
    ----------
    order : int
        The order n, 0 or 1.
    x : float
        The argument, positive.

    Returns
    -------
    float
        ``J_n(x)``.

    Examples
    --------
    >>> round(bessel_j(0, 1.0), 12), round(bessel_j(1, 1.0), 12)
    (0.765197686558, 0.440050585745)
    """
    return _bessel(order, x)[0]


def bessel_y(order: int, x: float) -> float:
    """Return the Bessel function of the second kind ``Y_n(x)``, n in (0, 1), x > 0.

    Parameters
    ----------
    order : int
        The order n, 0 or 1.
    x : float
        The argument, positive.

    Returns
    -------
    float
        ``Y_n(x)``.

    Examples
    --------
    >>> round(bessel_y(0, 1.0), 12), round(bessel_y(1, 1.0), 12)
    (0.088256964216, -0.7812128213)
    """
    return _bessel(order, x)[1]


def theodorsen(k: float) -> complex:
    """Theodorsen's lift deficiency function ``C(k)`` at the reduced frequency ``k``.

    ``C(k) = H1(k) / (H1(k) + i H0(k))``, with ``Hn = Jn - i Yn`` the Hankel
    function of the second kind; ``C(0) = 1``. Its phase is a lag (negative).

    Parameters
    ----------
    k : float
        The reduced frequency, a finite number >= 0.

    Returns
    -------
    complex
        ``C(k)``.

    Raises
    ------
    ProductError
        If ``k`` is not a finite number >= 0.

    Examples
    --------
    >>> value = theodorsen(1.0)
    >>> round(value.real, 4), round(value.imag, 4)
    (0.5394, -0.1003)
    """
    if not math.isfinite(k) or k < 0.0:
        raise ProductError(f"a reduced frequency is a finite number >= 0; it is {k!r}")
    if k == 0.0:
        return complex(1.0, 0.0)
    j0, y0 = _bessel(0, k)
    j1, y1 = _bessel(1, k)
    h0 = complex(j0, -y0)
    h1 = complex(j1, -y1)
    return h1 / (h1 + 1j * h0)


def sears(k: float) -> complex:
    """Sears's function ``S(k)`` at the reduced frequency ``k``, the gust referred to mid-chord.

    ``S(k) = (J0(k) - i J1(k)) C(k) + i J1(k)``; ``S(0) = 1``.

    Parameters
    ----------
    k : float
        The reduced frequency, a finite number >= 0.

    Returns
    -------
    complex
        ``S(k)``.

    Examples
    --------
    >>> round(abs(sears(0.0)), 12)
    1.0
    """
    if k == 0.0:
        return complex(1.0, 0.0)
    j0 = bessel_j(0, k)
    j1 = bessel_j(1, k)
    return complex(j0, -j1) * theodorsen(k) + 1j * j1
