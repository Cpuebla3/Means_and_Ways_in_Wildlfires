"""
Prepare MTT / fuel / feasibility rasters for firelinepath.

Why this module exists
----------------------
firelinepath 0.3 checks the feasibility grid like this::

    assert_eq!(mtt_matrix.rows,    feas_map[0].len(), "...");   // 888 vs 996
    assert_eq!(mtt_matrix.columns, feas_map[1].len(), "...");   // 996 vs 996

``feas_map[i].len()`` is the length of *row i*, i.e. the column count. So the
first assert compares the MTT row count against the feasibility column count,
and the second compares column count against the length of a different row.
The intended check is::

    assert_eq!(mtt_matrix.rows,    feas_map.len());
    assert_eq!(mtt_matrix.columns, feas_map[0].len());

For a rectangular NumPy mask every row has the same length, so the two asserts
demand ``rows == cols``. On Esperanza (888×996) no transpose can satisfy both:
flipping feasibility keeps the same pair of numbers, and flipping fuel instead
trips the (correct) fuel assert. That is why the error alternates between
"Feasibility matrix" and "Fuel matrix".

The MTT/fuel asserts compare rows-to-rows and columns-to-columns, so they are
correct and are left alone.

Two ways out
------------
1. Fix the Rust (two lines above) and rebuild the wheel. Then set
   ``FEASIBILITY_ASSERT_FIXED = True`` and rasters are passed through as-is.
2. Without rebuilding (the default here):
   * an all-feasible mask is passed as ``feasibility=None``, which skips the
     buggy assert entirely and is semantically identical;
   * a real mask forces a square pad to ``n×n`` (``n = max(rows, cols)``) so
     ``rows == cols`` makes the buggy assert coincide with the correct one.
     Row/column indices are preserved, so start/finish cells do not move.
"""
from __future__ import annotations

import numpy as np

# Flip to True after rebuilding firelinepath with the corrected asserts.
FEASIBILITY_ASSERT_FIXED = False


def _match_mtt_shape(mtt: np.ndarray, other: np.ndarray, name: str) -> np.ndarray:
    other = np.asarray(other)
    if other.shape == mtt.shape:
        return other
    if other.T.shape == mtt.shape:
        return other.T
    raise ValueError(f"{name} shape {other.shape} does not match MTT {mtt.shape}")


def _pad_square(arr: np.ndarray, fill) -> np.ndarray:
    rows, cols = arr.shape[:2]
    n = max(rows, cols)
    if rows == n and cols == n:
        return arr
    out = np.full((n, n), fill, dtype=arr.dtype)
    out[:rows, :cols] = arr
    return out


def align_fireline_rasters(mtt, fuel, feasibility=None, *, pad_square=False):
    """
    Return C-contiguous MTT / fuel / feasibility on one (row, col) layout.

    NaNs in MTT become ``+inf``: firelinepath calls ``NotNan::new`` on every
    cell and panics with "MTT cannot be NAN", and an unreachable cell is
    exactly what ``inf`` means here.

    With ``pad_square=True`` the grids are padded to ``n×n``; padded cells are
    ``inf`` arrival time, non-burnable fuel 99, and infeasible.
    """
    mtt = np.asarray(mtt, dtype=np.float64)
    if mtt.ndim != 2:
        raise ValueError(f"MTT must be 2-D, got shape {mtt.shape}")
    mtt = np.where(np.isnan(mtt), np.inf, mtt)

    fuel = np.asarray(_match_mtt_shape(mtt, fuel, "fuel"), dtype=np.int32)

    if feasibility is None:
        feasibility = np.ones(mtt.shape, dtype=bool)
    else:
        feasibility = np.asarray(
            _match_mtt_shape(mtt, np.asarray(feasibility), "feasibility"),
            dtype=bool,
        )

    if pad_square:
        mtt = _pad_square(mtt, np.inf)
        fuel = _pad_square(fuel, np.int32(99))
        feasibility = _pad_square(feasibility, False)

    return (
        np.ascontiguousarray(mtt, dtype=np.float64),
        np.ascontiguousarray(fuel, dtype=np.int32),
        np.ascontiguousarray(feasibility, dtype=bool),
    )


def call_fireline_between_two_points(
    *,
    start,
    mtt,
    fuel,
    fuel_clear_cost,
    feasibility=None,
    finish,
    clear_burning_penalty=1000000.0,
    distance_penalty=0.001,
    firefighter_fire_buffer_time=120,
):
    """
    Call firelinepath, working around its feasibility-assert bug.

    An all-True mask is sent as ``None`` (same meaning, no assert). A real
    mask on a non-square landscape is padded to square so the assert passes.
    """
    import firelinepath

    mtt, fuel, feasibility = align_fireline_rasters(mtt, fuel, feasibility)
    blocks_anything = not feasibility.all()

    if not blocks_anything:
        feasibility_arg = None
    elif FEASIBILITY_ASSERT_FIXED or mtt.shape[0] == mtt.shape[1]:
        feasibility_arg = feasibility
    else:
        mtt, fuel, feasibility_arg = align_fireline_rasters(
            mtt, fuel, feasibility, pad_square=True
        )

    return firelinepath.fireline_between_two_points(
        start=np.ascontiguousarray(start, dtype=int),
        mtt=mtt,
        fuel=fuel,
        fuel_clear_cost=fuel_clear_cost,
        feasibility=feasibility_arg,
        finish=np.ascontiguousarray(finish, dtype=int),
        clear_burning_penalty=clear_burning_penalty,
        distance_penalty=distance_penalty,
        firefighter_fire_buffer_time=firefighter_fire_buffer_time,
    )
