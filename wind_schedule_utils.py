
"""
Convert wind_schedule.csv into the list of
(t_start, t_end, speed, direction) tuples expected by the fire model.

Variable wind in this framework
--------------------------------
A schedule is a list of ``(start_min, end_min, speed, direction)`` bins.
``start_min`` is inclusive, ``end_min`` is exclusive.  Constructor kwargs
``wind_speed`` / ``wind_direction`` are used only when ``wind_schedule is None``.

How the different codes consume that schedule:

* **FIRE_MODEL_CUDA.SurrogateFireModelROS** – if a schedule is provided,
  ``run_multi_phase_arrival_with_ros`` advances one bin at a time (each bin
  is a constant-wind arrival-time solve).  Otherwise it uses the static
  speed/direction for the whole run.
* **WildfireModel / MCTS** – the live simulation keeps the *truth* schedule.
  At each MCTS decision, ``forecast_provider.get_forecast`` builds a μ/σ table
  from the background (climatology) means blended toward truth.  Rollouts
  sample a *future* schedule from that forecast and prepend the past truth
  bins (``sample_future_schedule``).  Clones must *not* share the live
  collector CSV (they pass ``data_collect_flag=False``).
* **ICS dynamic** (``ics_dynamic_NO_PLOTTING``) – head/heel/flank from the
  *current truth-schedule* direction (``current_wind``).
* **ICS dynamic mean** – same geometry, but direction comes from the latest
  forecast ``dir_mean`` (``prefer_forecast=True``).
* **ICS mean / truth lookahead** – same, evaluated at ``time + LOOKAHEAD``
  (usually one decision interval).
* **ICS ROS-weighted** – uses the live (truth) fire’s perimeter ROS.
* **ICS ROS-weighted mean** – temporarily injects a mean-only schedule into
  the fire object *only* for the ROS query, then restores truth.
* **ICS burned-buildings (truth / mean)** – precompute sector weights from a
  no-suppression arrival map under the truth or mean schedule.
* **ICS buildings** – static building counts; wind is unused for allocation.
* **groundcrew** – MTT buffer walk is sentinel-aware only when a schedule
  is present (arrival times can be inf in unburned / unburnable cells).

Use ``current_wind(model)`` whenever you need the speed/direction that is
actually active at ``model.time``.  Do **not** read ``model.wind_speed`` /
``model.wind_direction`` for scheduled runs: those stay at the constructor
dummies (often 0 mph / 220°) for the whole simulation.
"""
import numpy as np
import pandas as pd
from typing import List, Optional, Tuple

# def load_wind_schedule_from_csv(path="wind_schedule.csv", seed=None):
#     """
#     Read wind_schedule.csv and return a list of
#     (t_start, t_end, wind_speed_int, wind_dir_int) tuples.
#
#     • wind_speed is drawn from N(mean, std) → rounded → clamped ≥ 0 → int
#     • wind_direction is drawn from N(mean, std) → rounded → wrapped 0-359 → int
#     """
#     rng = np.random.default_rng(seed)
#     df  = pd.read_csv(path)
#
#     schedule = []
#     for row in df.itertuples():
#         # --- sample -----------------------------------------------------
#         wspd_f = rng.normal(row.speed_mean, row.speed_std)
#         wdir_f = rng.normal(row.dir_mean,   row.dir_std)
#
#         # --- convert to clean ints -------------------------------------
#         wspd_i = int(max(round(wspd_f), 0))       # no negative wind speeds
#         wdir_i = int(round(wdir_f)) % 360         # keep in 0-359
#
#         schedule.append((
#             int(row.start_min),
#             int(row.end_min),
#             wspd_i,
#             wdir_i
#         ))
#
#     return schedule
def load_wind_schedule_from_csv_mean(path="wind_schedule.csv"):
    df = pd.read_csv(path)
    return [(int(r.start_min), int(r.end_min),
             float(r.speed_mean), float(r.dir_mean) % 360)
            for r in df.itertuples()]

def sample_schedule_from_forecast(forecast_df: pd.DataFrame, seed=None):
    """
    Draw one concrete (speed, dir) from each row’s µ/σ.
    Returns list of (start_min, end_min, speed_int, dir_int).
    """
    rng = np.random.default_rng(seed)
    out = []
    for r in forecast_df.itertuples():
        spd = int(round(rng.normal(r.speed_mean, r.speed_std)))
        d   = int(round(rng.normal(r.dir_mean,   r.dir_std))) % 360
        out.append((int(r.start_min), int(r.end_min), max(spd, 0), d))
    return out


def sample_future_schedule(forecast_df: pd.DataFrame,
                           current_minute: int,
                           *, rng: np.random.Generator) -> list[tuple]:
    """
    Return a list of (t_start, t_end, speed, dir) tuples **starting at
    current_minute or later**.

    Every row in forecast_df must have the cols:
        start_min, end_min, speed_mean, speed_std, dir_mean, dir_std
    """
    future = forecast_df[forecast_df["end_min"] > current_minute]

    schedule = []
    for row in future.itertuples(index=False):
        # draw exactly one sample per forecast bin
        wspd = rng.normal(row.speed_mean, row.speed_std)
        wdir = rng.normal(row.dir_mean,   row.dir_std) % 360
        schedule.append((
            int(row.start_min),
            int(row.end_min),
            float(max(wspd, 0.0)),
            float(wdir)
        ))
    return schedule



def _angular_diff(a: float, b: float) -> float:
    """Shortest signed difference between two headings (deg)."""
    d = (a - b + 180) % 360 - 180
    return abs(d)

def load_wind_schedule_from_csv_random(path="wind_schedule.csv", *, seed=None):
    """
    Return list[(start, end, speed, dir)].
    If *seed* is None → means only.  Otherwise draw one sample per row.
    """
    rng = None if seed is None else np.random.default_rng(seed)
    df  = pd.read_csv(path)

    if rng is None:                     # deterministic “mean” schedule
        return [(int(r.start_min), int(r.end_min),
                 float(r.speed_mean), float(r.dir_mean) % 360)
                for r in df.itertuples()]

    out = []
    for r in df.itertuples():
        spd = max(rng.normal(r.speed_mean, r.speed_std), 0.0)
        d   = rng.normal(r.dir_mean,  r.dir_std) % 360.0
        out.append((int(r.start_min), int(r.end_min), spd, d))
    return out



def load_wind_schedule_from_csv_sigma(
    path: str = "wind_schedule.csv",
    *,
    sigma: float = 3.0,
    seed: int | None = None
) -> List[Tuple[int, int, float, float]]:
    """
    Return the **truth** schedule with every (speed, dir) pushed exactly
    ± sigma·std away from the mean.

    Parameters
    ----------
    path   : CSV with the usual columns: start_min, end_min,
             speed_mean, speed_std, dir_mean, dir_std
    sigma  : How many standard deviations away from the mean
    seed   : If given, results are reproducible (changes the ± sign pattern)

    Notes
    -----
    • Speed is clamped at ≥ 0 after the offset.
    • Direction is wrapped into 0–359 deg after the offset.
    """
    rng = np.random.default_rng(seed)
    df  = pd.read_csv(path)

    out = []
    for r in df.itertuples(index=False):
        # decide sign independently for speed and direction
        sign_spd = rng.choice((-1, 1))
        sign_dir = rng.choice((-1, 1))

        spd = r.speed_mean + sign_spd * sigma * r.speed_std
        spd = max(spd, 0.0)                          # no negative wind speed

        d   = (r.dir_mean + sign_dir * sigma * r.dir_std) % 360.0

        out.append((int(r.start_min), int(r.end_min), float(spd), float(d)))
    return out


def _print_schedule(
    schedule: List[Tuple[int, int, float, float]],
    title: str = "Truth schedule"
) -> None:
    """
    Nicely print a list of (t_start, t_end, speed, dir) tuples.
    """
    df = pd.DataFrame(schedule, columns=["start", "end", "speed", "dir"])
    print(f"\n{title}")
    print(df.to_string(index=False, float_format=lambda x: f"{x:8.3f}"))


def wind_at_time(
    schedule,
    t: float,
    *,
    fallback_speed: float = 0.0,
    fallback_direction: float = 0.0,
) -> Tuple[float, float]:
    """
    Return ``(speed, direction_deg)`` active at minute *t*.

    Bins are ``[start, end)``.  Times before the first bin use that bin;
    times at/after the last bin's ``end`` use the last bin.  A missing /
    empty schedule falls back to the static constructor values.
    """
    if not schedule:
        return float(fallback_speed), float(fallback_direction) % 360.0

    t = float(t)
    first = schedule[0]
    if t < first[0]:
        return float(first[2]), float(first[3]) % 360.0

    for start, end, spd, wdir in schedule:
        if start <= t < end:
            return float(spd), float(wdir) % 360.0

    last = schedule[-1]
    return float(last[2]), float(last[3]) % 360.0


def _forecast_wind_at_time(forecast_df, t: float) -> Optional[Tuple[float, float]]:
    """Return ``(speed_mean, dir_mean)`` covering *t*, or ``None`` if no table."""
    if forecast_df is None:
        return None
    try:
        if forecast_df.empty:
            return None
    except (AttributeError, TypeError, ValueError):
        return None

    t = float(t)
    mask = (forecast_df["start_min"] <= t) & (t < forecast_df["end_min"])
    row = forecast_df.loc[mask].iloc[0] if mask.any() else forecast_df.iloc[-1]
    return float(row["speed_mean"]), float(row["dir_mean"]) % 360.0


def current_wind(
    model,
    *,
    t: Optional[float] = None,
    lookahead: float = 0.0,
    prefer_forecast: bool = False,
) -> Tuple[float, float]:
    """
    Speed/direction a planner should use at ``t + lookahead`` (minutes).

    Parameters
    ----------
    prefer_forecast
        If True and ``model.latest_forecast_df`` is set, use that table's
        μ values (ICS-mean / ICS-mean-lookahead).  Otherwise use the model's
        truth ``wind_schedule``, then static ``wind_speed`` / ``wind_direction``.
    """
    query_t = (model.time if t is None else t) + lookahead

    if prefer_forecast:
        fc = _forecast_wind_at_time(
            getattr(model, "latest_forecast_df", None), query_t
        )
        if fc is not None:
            return fc

    return wind_at_time(
        getattr(model, "wind_schedule", None),
        query_t,
        fallback_speed=getattr(model, "wind_speed", 0.0),
        fallback_direction=getattr(model, "wind_direction", 0.0),
    )