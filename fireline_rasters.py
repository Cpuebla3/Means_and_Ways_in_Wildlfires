"""
Align MTT / fuel / feasibility rasters before calling firelinepath.

The Esperanza landscape (cali_test_big_enhanced.tif) is 888 rows × 996 cols.
firelinepath's Rust binding compares the first axis of MTT vs feasibility; a
Fortran-order or width-major copy is seen as 996 vs 888 and panics:

    MTT matrix is not of same size as Feasibility matrix
    left: 888  right: 996
"""
from __future__ import annotations

import numpy as np


def align_fireline_rasters(mtt, fuel, feasibility=None):
    """
    Return C-contiguous (row, col) copies of MTT, fuel, and feasibility
    that all share MTT's shape.
    """
    mtt = np.asarray(mtt)
    fuel = np.asarray(fuel)
    if mtt.ndim != 2 or fuel.ndim != 2:
        raise ValueError(
            f"MTT and fuel must be 2-D (got MTT {mtt.shape}, fuel {fuel.shape})"
        )
    if fuel.shape != mtt.shape:
        if fuel.T.shape == mtt.shape:
            fuel = fuel.T
        else:
            raise ValueError(
                f"fuel shape {fuel.shape} does not match MTT {mtt.shape}"
            )
    if feasibility is None:
        feasibility = np.ones(mtt.shape, dtype=bool)
    else:
        feasibility = np.asarray(feasibility)
        if feasibility.shape != mtt.shape:
            if feasibility.T.shape == mtt.shape:
                feasibility = feasibility.T
            else:
                raise ValueError(
                    f"feasibility shape {feasibility.shape} does not match MTT {mtt.shape}"
                )
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
    """Call firelinepath after forcing matching C-contiguous raster shapes."""
    import firelinepath
    print('mtt_shape',mtt.shape)
    print('fuel_shape', fuel.shape)
    print('feasibility_shape', feasibility.shape)
    mtt, fuel, feasibility = align_fireline_rasters(mtt, fuel, feasibility)
    # mtt = mtt.T
    # fuel = fuel.T
    print('mtt_shape',mtt.shape)
    print('fuel_shape', fuel.shape)
    print('feasibility_shape', feasibility.shape)
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
