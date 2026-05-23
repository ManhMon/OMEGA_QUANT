"""
Tests for Phase 3.1 Label Engine
"""

import unittest
import numpy as np
import pandas as pd
import pytest
from omega.quant.label_engine import (
    generate_forward_return_labels,
    generate_binary_labels,
    generate_quantile_labels,
    validate_label_availability
)

class TestLabelEngine(unittest.TestCase):
    
    def setUp(self):
        self.prices_list = [100.0, 102.0, 105.0, 103.0, 108.0]
        self.prices_ser = pd.Series(self.prices_list)
        self.prices_arr = np.array(self.prices_list)

    def test_forward_returns_series(self):
        """1. Test forward returns with pandas Series"""
        horizon = 2
        returns = generate_forward_return_labels(self.prices_ser, horizon)
        
        self.assertIsInstance(returns, pd.Series)
        # return[0] = (105-100)/100 = 0.05
        # return[1] = (103-102)/102 = 0.0098...
        # return[2] = (108-105)/105 = 0.0285...
        self.assertAlmostEqual(returns[0], 0.05)
        self.assertAlmostEqual(returns[1], 0.00980392, places=7)
        self.assertTrue(pd.isna(returns[3]))
        self.assertTrue(pd.isna(returns[4]))

    def test_forward_returns_numpy(self):
        """2. Test forward returns with numpy array"""
        horizon = 1
        returns = generate_forward_return_labels(self.prices_arr, horizon)
        
        self.assertIsInstance(returns, np.ndarray)
        # return[0] = (102-100)/100 = 0.02
        self.assertAlmostEqual(returns[0], 0.02)
        self.assertTrue(np.isnan(returns[-1]))
        self.assertEqual(len(returns), len(self.prices_arr))

    def test_pit_horizon_nan(self):
        """3. Test PIT constraint: last 'horizon' values must be NaN"""
        horizon = 3
        returns = generate_forward_return_labels(self.prices_ser, horizon)
        
        # indices 0, 1 should have values
        # indices 2, 3, 4 should be NaN (horizon=3)
        self.assertFalse(pd.isna(returns[0]))
        self.assertFalse(pd.isna(returns[1]))
        self.assertTrue(pd.isna(returns[2]))
        self.assertTrue(pd.isna(returns[3]))
        self.assertTrue(pd.isna(returns[4]))

    def test_binary_labels(self):
        """4. Test binary labels with threshold"""
        returns = pd.Series([0.05, -0.02, 0.01, np.nan])
        
        # Default threshold 0.0
        labels_0 = generate_binary_labels(returns, threshold=0.0)
        np.testing.assert_array_equal(labels_0[:3], [1.0, 0.0, 1.0])
        self.assertTrue(pd.isna(labels_0[3]))
        
        # High threshold 0.02
        labels_high = generate_binary_labels(returns, threshold=0.02)
        np.testing.assert_array_equal(labels_high[:3], [1.0, 0.0, 0.0])

    def test_quantile_labels(self):
        """5. Test quantile labels distribution"""
        # 6 values, 3 quantiles -> 2 per bucket
        returns = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
        labels = generate_quantile_labels(returns, n_quantiles=3)
        
        # Expecting labels: [0, 0, 1, 1, 2, 2]
        np.testing.assert_array_equal(labels, [0.0, 0.0, 1.0, 1.0, 2.0, 2.0])
        
        # Test with NaNs
        returns_nan = pd.Series([0.1, np.nan, 0.3, 0.5, 0.6])
        labels_nan = generate_quantile_labels(returns_nan, n_quantiles=2)
        # Values [0.1, 0.3, 0.5, 0.6]. Median between 0.3 and 0.5.
        # Expecting labels: [0, NaN, 0, 1, 1]
        self.assertEqual(labels_nan[0], 0.0)
        self.assertTrue(pd.isna(labels_nan[1]))
        self.assertEqual(labels_nan[4], 1.0)

    def test_validate_availability_valid(self):
        """6. Test label availability validation (valid case)"""
        dates = pd.date_range('2020-01-01', periods=5)
        # Positions: 0, 1, 2, 3, 4 (dates: 01-01, 01-02, 01-03, 01-04, 01-05)
        # With horizon=2:
        # - Label at pos 0 available at pos 3 (01-04)
        # - Label at pos 1 available at pos 4 (01-05)
        # At decision time pos 3 (01-04), only label at pos 0 should exist
        labels = pd.Series([1, np.nan, np.nan, np.nan, np.nan], index=dates)
        
        # At 2020-01-04 (pos 3), horizon=2
        # forbidden_start = 3 - 2 = 1
        # labels[1:] should all be NaN -> valid
        self.assertTrue(validate_label_availability(labels, '2020-01-04', horizon=2))

    def test_validate_availability_leakage(self):
        """7. Test label availability validation (leakage case)"""
        dates = pd.date_range('2020-01-01', periods=5)
        # Positions: 0, 1, 2, 3, 4
        # At decision time pos 3 (01-04), horizon=2
        # forbidden_start = 3 - 2 = 1
        # Label at pos 1 should be NaN (not available until pos 4)
        # But we have a label at pos 1 -> LEAKAGE!
        labels = pd.Series([1, 1, np.nan, np.nan, np.nan], index=dates)
        
        self.assertFalse(validate_label_availability(labels, '2020-01-04', horizon=2))

    def test_error_handling(self):
        """8. Test error handling for invalid inputs"""
        # Negative horizon
        with self.assertRaises(ValueError):
            generate_forward_return_labels(self.prices_ser, horizon=-1)
            
        # Prices with NaN
        prices_nan = self.prices_ser.copy()
        prices_nan[0] = np.nan
        with self.assertRaises(ValueError):
            generate_forward_return_labels(prices_nan, horizon=1)
            
        # Zero prices
        prices_zero = self.prices_ser.copy()
        prices_zero[0] = 0.0
        with self.assertRaises(ValueError):
            generate_forward_return_labels(prices_zero, horizon=1)
            
        # Insufficient data for quantiles
        with self.assertRaises(ValueError):
            generate_quantile_labels(pd.Series([0.1, np.nan]), n_quantiles=5)

if __name__ == '__main__':
    unittest.main()
