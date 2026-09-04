"""
Tests for the firelinepath raster workaround (Esperanza 888×996).

``_rust_feasibility_assert`` mirrors firelinepath 0.3 src/lib.rs so the tests
show which argument shapes survive the library's buggy check without needing
the compiled wheel.
"""
from __future__ import annotations

import unittest

import numpy as np

import fireline_rasters
from fireline_rasters import align_fireline_rasters

ROWS, COLS = 888, 996


def _rust_feasibility_assert(mtt, feasibility):
    """
    Reproduce firelinepath's check:

        assert_eq!(mtt_matrix.rows,    feas_map[0].len());
        assert_eq!(mtt_matrix.columns, feas_map[1].len());

    ``feas_map[i].len()`` is a row length, i.e. the column count.
    """
    if feasibility is None:
        return
    rows, cols = np.asarray(mtt).shape
    feas = np.asarray(feasibility)
    if rows != len(feas[0]):
        raise AssertionError(
            f"MTT matrix is not of same size as Feasibility matrix "
            f"left: {rows} right: {len(feas[0])}"
        )
    if cols != len(feas[1]):
        raise AssertionError(
            f"MTT matrix is not of same size as Feasibility matrix "
            f"left: {cols} right: {len(feas[1])}"
        )


def _rust_fuel_assert(mtt, fuel):
    """The fuel check is correct: rows-to-rows and columns-to-columns."""
    mtt = np.asarray(mtt)
    fuel = np.asarray(fuel)
    if mtt.shape[0] != fuel.shape[0] or mtt.shape[1] != fuel.shape[1]:
        raise AssertionError("MTT matrix is not of same size as Fuel matrix")


class RustAssertReproductionTests(unittest.TestCase):
    """No transpose of a rectangular mask can satisfy the buggy assert."""

    def test_every_transpose_combination_still_fails(self):
        mtt = np.zeros((ROWS, COLS))
        fuel = np.ones((ROWS, COLS), dtype=np.int32)
        feas = np.ones((ROWS, COLS), dtype=bool)

        for label, m, f, fe in [
            ("as-is", mtt, fuel, feas),
            ("feas.T", mtt, fuel, feas.T),
            ("fuel.T", mtt, fuel.T, feas),
            ("mtt.T", mtt.T, fuel, feas),
            ("mtt.T+feas.T", mtt.T, fuel, feas.T),
            ("all.T", mtt.T, fuel.T, feas.T),
        ]:
            with self.subTest(combination=label):
                with self.assertRaises(AssertionError):
                    _rust_fuel_assert(m, f)
                    _rust_feasibility_assert(m, fe)

    def test_all_true_mask_sent_as_none_passes(self):
        mtt = np.zeros((ROWS, COLS))
        _rust_feasibility_assert(mtt, None)

    def test_square_padded_mask_passes(self):
        mtt = np.zeros((ROWS, COLS))
        fuel = np.ones((ROWS, COLS), dtype=np.int32)
        feas = np.ones((ROWS, COLS), dtype=bool)
        feas[10:20, 10:20] = False

        m2, f2, feas2 = align_fireline_rasters(mtt, fuel, feas, pad_square=True)
        _rust_fuel_assert(m2, f2)
        _rust_feasibility_assert(m2, feas2)


class AlignTests(unittest.TestCase):
    def test_no_padding_by_default(self):
        mtt = np.zeros((ROWS, COLS))
        fuel = np.ones((ROWS, COLS), dtype=np.int32, order="F")
        m2, f2, feas2 = align_fireline_rasters(mtt, fuel)
        self.assertEqual(m2.shape, (ROWS, COLS))
        self.assertEqual(f2.shape, (ROWS, COLS))
        self.assertEqual(feas2.shape, (ROWS, COLS))
        self.assertTrue(m2.flags["C_CONTIGUOUS"])
        self.assertTrue(f2.flags["C_CONTIGUOUS"])

    def test_pad_square_preserves_indices_and_blocks_padding(self):
        mtt = np.arange(ROWS * COLS, dtype=np.float64).reshape(ROWS, COLS)
        fuel = np.full((ROWS, COLS), 102, dtype=np.int32)
        m2, f2, feas2 = align_fireline_rasters(mtt, fuel, pad_square=True)

        self.assertEqual(m2.shape, (COLS, COLS))
        np.testing.assert_array_equal(m2[:ROWS, :COLS], mtt)
        self.assertTrue(np.isinf(m2[ROWS:, :]).all())
        self.assertTrue((f2[ROWS:, :] == 99).all())
        self.assertTrue((feas2[ROWS:, :] == False).all())  # noqa: E712
        self.assertTrue(feas2[:ROWS, :].all())

    def test_nan_mtt_becomes_inf(self):
        """firelinepath panics with 'MTT cannot be NAN'."""
        mtt = np.array([[np.nan, 1.0], [2.0, 3.0]])
        fuel = np.ones((2, 2), dtype=np.int32)
        m2, _, _ = align_fireline_rasters(mtt, fuel)
        self.assertFalse(np.isnan(m2).any())
        self.assertTrue(np.isinf(m2[0, 0]))

    def test_transposed_fuel_is_rotated_back(self):
        mtt = np.zeros((ROWS, COLS))
        fuel = np.full((COLS, ROWS), 102, dtype=np.int32)
        m2, f2, _ = align_fireline_rasters(mtt, fuel)
        self.assertEqual(f2.shape, m2.shape)
        _rust_fuel_assert(m2, f2)

    def test_mismatched_shape_raises_clear_error(self):
        mtt = np.zeros((ROWS, COLS))
        fuel = np.ones((10, 11), dtype=np.int32)
        with self.assertRaises(ValueError):
            align_fireline_rasters(mtt, fuel)


class CallWrapperTests(unittest.TestCase):
    """Check what call_fireline_between_two_points forwards to Rust."""

    def setUp(self):
        self.calls = []

        class FakeFirelinepath:
            def fireline_between_two_points(inner, **kwargs):  # noqa: N805
                self.calls.append(kwargs)
                _rust_fuel_assert(kwargs["mtt"], kwargs["fuel"])
                _rust_feasibility_assert(kwargs["mtt"], kwargs["feasibility"])
                return [([0, 0], [0.0, 0.0, 0.0, 1.0, 1.0])]

        import sys

        self._saved = sys.modules.get("firelinepath")
        sys.modules["firelinepath"] = FakeFirelinepath()

    def tearDown(self):
        import sys

        if self._saved is None:
            sys.modules.pop("firelinepath", None)
        else:
            sys.modules["firelinepath"] = self._saved

    def _call(self, feasibility):
        return fireline_rasters.call_fireline_between_two_points(
            start=np.array([444, 498]),
            mtt=np.zeros((ROWS, COLS)),
            fuel=np.ones((ROWS, COLS), dtype=np.int32),
            fuel_clear_cost={1: 0.157},
            feasibility=feasibility,
            finish=np.array([500, 600]),
        )

    def test_all_feasible_mask_is_forwarded_as_none_unpadded(self):
        self._call(np.ones((ROWS, COLS), dtype=bool))
        kwargs = self.calls[-1]
        self.assertIsNone(kwargs["feasibility"])
        self.assertEqual(kwargs["mtt"].shape, (ROWS, COLS))

    def test_omitted_feasibility_is_forwarded_as_none(self):
        self._call(None)
        self.assertIsNone(self.calls[-1]["feasibility"])

    def test_real_mask_is_padded_square(self):
        feas = np.ones((ROWS, COLS), dtype=bool)
        feas[100:200, 100:200] = False
        self._call(feas)
        kwargs = self.calls[-1]
        self.assertEqual(kwargs["mtt"].shape, (COLS, COLS))
        self.assertEqual(kwargs["feasibility"].shape, (COLS, COLS))
        self.assertFalse(kwargs["feasibility"][150, 150])

    def test_real_mask_not_padded_when_rust_is_fixed(self):
        feas = np.ones((ROWS, COLS), dtype=bool)
        feas[100:200, 100:200] = False
        fireline_rasters.FEASIBILITY_ASSERT_FIXED = True
        try:
            with self.assertRaises(AssertionError):
                self._call(feas)
        finally:
            fireline_rasters.FEASIBILITY_ASSERT_FIXED = False
        self.assertEqual(self.calls[-1]["mtt"].shape, (ROWS, COLS))


if __name__ == "__main__":
    unittest.main()
