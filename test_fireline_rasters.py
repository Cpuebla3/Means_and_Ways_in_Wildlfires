"""Shape tests for firelinepath raster padding (Esperanza 888×996)."""
from __future__ import annotations

import unittest

import numpy as np

from fireline_rasters import align_fireline_rasters


class FirelineRasterAlignTests(unittest.TestCase):
    def test_esperanza_is_padded_to_square_996(self):
        rows, cols = 888, 996
        mtt = np.arange(rows * cols, dtype=np.float64).reshape(rows, cols)
        fuel = np.ones((rows, cols), dtype=np.int32, order="F")
        feasibility = np.ones((rows, cols), dtype=bool, order="F")

        m2, f2, feas2 = align_fireline_rasters(mtt, fuel, feasibility)
        self.assertEqual(m2.shape, (996, 996))
        self.assertEqual(f2.shape, (996, 996))
        self.assertEqual(feas2.shape, (996, 996))
        self.assertEqual(m2.shape[0], m2.shape[1])
        self.assertEqual(m2.shape[0], feas2.shape[1])
        self.assertTrue(m2.flags["C_CONTIGUOUS"])
        self.assertTrue(feas2.flags["C_CONTIGUOUS"])
        np.testing.assert_array_equal(m2[:rows, :cols], mtt)
        self.assertTrue(np.isinf(m2[888:, :]).all())
        self.assertTrue((feas2[888:, :] == 0).all())
        self.assertTrue((feas2[:, 996:] == 0).all() if feas2.shape[1] > 996 else True)

    def test_transposed_fuel_is_rotated_then_padded(self):
        mtt = np.zeros((888, 996), dtype=np.float64)
        fuel = np.full((996, 888), 102, dtype=np.int32)
        m2, f2, feas2 = align_fireline_rasters(mtt, fuel)
        self.assertEqual(m2.shape, (996, 996))
        self.assertTrue(np.all(f2[:888, :996] == 102))
        self.assertTrue(np.all(f2[888:, :] == 99))

    def test_square_input_is_unchanged_shape(self):
        mtt = np.zeros((10, 10), dtype=np.float64)
        fuel = np.ones((10, 10), dtype=np.int32)
        m2, f2, feas2 = align_fireline_rasters(mtt, fuel)
        self.assertEqual(m2.shape, (10, 10))
        self.assertEqual(f2.shape, (10, 10))
        self.assertEqual(feas2.shape, (10, 10))


if __name__ == "__main__":
    unittest.main()
