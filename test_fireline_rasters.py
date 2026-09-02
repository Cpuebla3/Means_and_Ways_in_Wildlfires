"""Shape/layout tests for firelinepath raster alignment (Esperanza 888×996)."""
from __future__ import annotations

import unittest

import numpy as np

from fireline_rasters import align_fireline_rasters


class FirelineRasterAlignTests(unittest.TestCase):
    def test_fortran_fuel_matches_c_order_mtt_esperanza_shape(self):
        rows, cols = 888, 996
        mtt = np.arange(rows * cols, dtype=np.float64).reshape(rows, cols)
        fuel = np.ones((rows, cols), dtype=np.int32, order="F")
        feasibility = np.ones((rows, cols), dtype=bool, order="F")

        self.assertEqual(mtt.shape[0], 888)
        self.assertEqual(feasibility.shape[1], 996)

        m2, f2, feas2 = align_fireline_rasters(mtt, fuel, feasibility)
        self.assertEqual(m2.shape, (888, 996))
        self.assertEqual(f2.shape, m2.shape)
        self.assertEqual(feas2.shape, m2.shape)
        self.assertTrue(m2.flags["C_CONTIGUOUS"])
        self.assertTrue(f2.flags["C_CONTIGUOUS"])
        self.assertTrue(feas2.flags["C_CONTIGUOUS"])

    def test_transposed_fuel_is_rotated_back_to_mtt(self):
        mtt = np.zeros((888, 996), dtype=np.float64)
        fuel = np.full((996, 888), 102, dtype=np.int32)
        m2, f2, feas2 = align_fireline_rasters(mtt, fuel)
        self.assertEqual(m2.shape, (888, 996))
        self.assertEqual(f2.shape, (888, 996))
        self.assertEqual(feas2.shape, (888, 996))
        self.assertTrue(np.all(f2 == 102))

    def test_ones_like_fuel_does_not_keep_mismatched_first_axis(self):
        """Reproduce the old _rough_line_minutes construction, then align."""
        raw_mtt = np.zeros((888, 996), dtype=np.float64)
        fuel = np.ones((888, 996), dtype=np.int32, order="F")
        feasibility = np.ones_like(fuel, dtype=bool)
        # Before alignment the first axes can look like 888 vs 996 to Rust
        # if one array is read column-major.
        m2, f2, feas2 = align_fireline_rasters(raw_mtt, fuel, feasibility)
        self.assertEqual(m2.shape[0], feas2.shape[0])
        self.assertEqual(m2.shape[1], feas2.shape[1])


if __name__ == "__main__":
    unittest.main()
