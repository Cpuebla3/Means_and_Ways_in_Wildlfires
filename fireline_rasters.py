"""
Prepare MTT / fuel / feasibility rasters for firelinepath.

Esperanza (cali_test_big_enhanced.tif) is 888 rows × 996 cols. firelinepath
0.3 asserts at src/lib.rs:517:

    MTT matrix is not of same size as Feasibility matrix
    left: 888
    right: 996

That is the grid *height* vs *width*, not a leftover C-vs-F copy. Making both
arrays C-contiguous (888, 996) does not change those two numbers. The binding
compares one matrix's row count to the other's column count — a check that
only passes on square landscapes.

Workaround: pad every raster to n×n with n = max(rows, cols). Start/finish
cells stay in the original extent; padded cells are +inf / infeasible.
"""
from __future__ import annotations

import numpy as np


def _match_mtt_shape(mtt: np.ndarray, other: np.ndarray, name: str) -> np.ndarray:
    other = np.asarray(other)
    if other.shape == mtt.shape:
        return other
    if other.T.shape == mtt.shape:
        return other.T
    raise ValueError(f"{name} shape {other.shape} does not match MTT {mtt.shape}")


def _pad_square(arr: np.ndarray, fill):
    rows, cols = arr.shape[:2]
    n = max(rows, cols)
    if rows == n and cols == n:
        return arr
    out = np.full((n, n), fill, dtype=arr.dtype)
    out[:rows, :cols] = arr
    return out


def align_fireline_rasters(mtt, fuel, feasibility=None):
    """
    Return C-contiguous square copies of MTT, fuel, and feasibility.

    On Esperanza the result is (996, 996). Original data occupy [:888, :996].
    """
    mtt = np.asarray(mtt, dtype=np.float64)
    if mtt.ndim != 2:
        raise ValueError(f"MTT must be 2-D, got shape {mtt.shape}")
    fuel = np.asarray(_match_mtt_shape(mtt, fuel, "fuel"), dtype=np.int32)
    if feasibility is None:
        feasibility = np.ones(mtt.shape, dtype=bool)
    else:
        feasibility = np.asarray(
            _match_mtt_shape(mtt, np.asarray(feasibility), "feasibility"),
            dtype=bool,
        )

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
    feasibility,
    finish,
    clear_burning_penalty=1000000.0,
    distance_penalty=0.001,
    firefighter_fire_buffer_time=120,
):
    """Call firelinepath after padding rasters to a square C-contiguous layout."""
    import firelinepath

    mtt, fuel, feasibility = align_fireline_rasters(mtt, fuel, feasibility)
    return firelinepath.fireline_between_two_points(
        start=np.ascontiguousarray(start, dtype=int),
        mtt=mtt,
        fuel=fuel,
        fuel_clear_cost=fuel_clear_cost,
        feasibility=feasibility,
        finish=np.ascontiguousarray(finish, dtype=int),
        clear_burning_penalty=clear_burning_penalty,
        distance_penalty=distance_penalty,
        firefighter_fire_buffer_time=firefighter_fire_buffer_time,
    )
