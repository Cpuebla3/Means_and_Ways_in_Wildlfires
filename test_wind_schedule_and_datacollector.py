"""Tests for wind-schedule lookup and collector CSV schema handling."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from datacollector_io import (
    CollectorSchemaError,
    append_datacollector_frame,
    read_partial_data_csv,
    reset_partial_data_files,
    save_final_collected_results,
)
from wind_schedule_utils import current_wind, wind_at_time


SCHEDULE = [
    (0, 120, 10.0, 180.0),
    (120, 240, 20.0, 90.0),
    (240, 360, 15.0, 45.0),
]


class WindLookupTests(unittest.TestCase):
    def test_wind_at_time_bins_are_half_open(self):
        self.assertEqual(wind_at_time(SCHEDULE, 0), (10.0, 180.0))
        self.assertEqual(wind_at_time(SCHEDULE, 119), (10.0, 180.0))
        self.assertEqual(wind_at_time(SCHEDULE, 120), (20.0, 90.0))
        self.assertEqual(wind_at_time(SCHEDULE, 240), (15.0, 45.0))

    def test_wind_at_time_before_and_after_schedule(self):
        self.assertEqual(wind_at_time(SCHEDULE, -10), (10.0, 180.0))
        self.assertEqual(wind_at_time(SCHEDULE, 400), (15.0, 45.0))

    def test_wind_at_time_static_fallback(self):
        spd, d = wind_at_time(None, 50, fallback_speed=7, fallback_direction=370)
        self.assertEqual(spd, 7.0)
        self.assertEqual(d, 10.0)

    def test_current_wind_reads_truth_schedule_not_constructor_dummies(self):
        model = SimpleNamespace(
            time=150,
            wind_speed=0,
            wind_direction=220,
            wind_schedule=SCHEDULE,
            latest_forecast_df=None,
        )
        self.assertEqual(current_wind(model), (20.0, 90.0))

    def test_current_wind_lookahead_uses_future_bin(self):
        model = SimpleNamespace(
            time=150,
            wind_speed=0,
            wind_direction=220,
            wind_schedule=SCHEDULE,
            latest_forecast_df=None,
        )
        self.assertEqual(current_wind(model, lookahead=120), (15.0, 45.0))

    def test_prefer_forecast_then_truth_fallback(self):
        fc = pd.DataFrame(
            [
                dict(start_min=120, end_min=240, speed_mean=3.5, dir_mean=12.0),
                dict(start_min=240, end_min=360, speed_mean=4.0, dir_mean=30.0),
            ]
        )
        model = SimpleNamespace(
            time=150,
            wind_speed=0,
            wind_direction=220,
            wind_schedule=SCHEDULE,
            latest_forecast_df=fc,
        )
        self.assertEqual(current_wind(model, prefer_forecast=True), (3.5, 12.0))
        self.assertEqual(
            current_wind(model, lookahead=120, prefer_forecast=True),
            (4.0, 30.0),
        )
        model.latest_forecast_df = None
        self.assertEqual(current_wind(model, prefer_forecast=True), (20.0, 90.0))


class CollectorCsvTests(unittest.TestCase):
    def test_legacy_append_of_5_cols_onto_3_cols_raises_parser_error(self):
        """Reproduce the dashboard_NO_PLOTTING ParserError after adding wind columns."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "Partial_Data_Loading.csv"
            old = pd.DataFrame({"Agents_by_type": ["{}"], "Drops": ["[]"]})
            old.to_csv(path, mode="w", header=True, index=True)
            new = pd.DataFrame(
                {
                    "Agents_by_type": ["{}"],
                    "Drops": ["[]"],
                    "wind_speed": [18.68],
                    "wind_direction": [258.28],
                }
            )
            new.to_csv(path, mode="a", header=False, index=True)
            with self.assertRaises(pd.errors.ParserError) as ctx:
                pd.read_csv(path)
            msg = str(ctx.exception)
            self.assertIn("Expected 3 fields", msg)
            self.assertIn("saw 5", msg)

    def test_ragged_file_is_recovered_with_wind_columns(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "Model_Partial_Data_Loading.csv"
            old = pd.DataFrame({"Agents_by_type": ['{"C130J": 1}'], "Drops": ["[]"]})
            old.to_csv(path, mode="w", header=True, index=True)
            new = pd.DataFrame(
                {
                    "Agents_by_type": ['{"C130J": 1}'],
                    "Drops": ["[]"],
                    "wind_speed": [18.68],
                    "wind_direction": [258.28],
                }
            )
            new.to_csv(path, mode="a", header=False, index=True)
            df = read_partial_data_csv(path)
            self.assertIn("wind_speed", df.columns)
            self.assertIn("wind_direction", df.columns)
            self.assertGreaterEqual(len(df), 1)
            last = df.iloc[-1]
            self.assertEqual(float(last["wind_speed"]), 18.68)
            self.assertEqual(float(last["wind_direction"]), 258.28)

    def test_append_rejects_schema_mismatch_instead_of_corrupting(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "partial.csv"
            append_datacollector_frame(
                pd.DataFrame({"Agents_by_type": ["{}"], "Drops": ["[]"]}),
                path=path,
            )
            with self.assertRaises(CollectorSchemaError):
                append_datacollector_frame(
                    pd.DataFrame(
                        {
                            "Time": [10],
                            "Agents_by_type": ["{}"],
                            "Drops": ["[]"],
                            "wind_speed": [10.0],
                            "wind_direction": [180.0],
                        }
                    ),
                    path=path,
                )

    def test_reset_then_five_column_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path.cwd()
            try:
                import os

                os.chdir(td)
                leftover = Path("Partial_Data_Loading.csv")
                pd.DataFrame({"Agents_by_type": ["{}"], "Drops": ["[]"]}).to_csv(
                    leftover, index=True
                )
                reset_partial_data_files()
                self.assertFalse(leftover.exists())

                frame = pd.DataFrame(
                    {
                        "Time": [0, 1],
                        "Agents_by_type": ['{"GroundCrewAgent": 2}', '{"GroundCrewAgent": 2}'],
                        "Drops": ["[]", "[]"],
                        "wind_speed": [10.0, 20.0],
                        "wind_direction": [180.0, 90.0],
                    }
                )
                dest = Path("Model_Partial_Data_Loading.csv")
                append_datacollector_frame(frame.iloc[[0]], path=dest)
                append_datacollector_frame(frame.iloc[[1]], path=dest)
                out = Path("Final_Collected_Results.csv")
                saved = save_final_collected_results(out, path=dest)
                self.assertEqual(saved, out)
                result = pd.read_csv(out)
                self.assertListEqual(
                    list(result.columns),
                    ["Time", "Agents_by_type", "Drops", "wind_speed", "wind_direction"],
                )
                self.assertEqual(len(result), 2)
                self.assertEqual(result.iloc[1]["wind_speed"], 20.0)
                self.assertFalse(dest.exists())
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
