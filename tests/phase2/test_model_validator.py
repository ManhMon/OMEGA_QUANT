import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from omega.core.validator import ModelValidator

class TestModelValidator(unittest.TestCase):
    def setUp(self):
        self.validator = ModelValidator(target_col='target', embargo_days=2)
        
        # Create dummy data
        dates = pd.date_range('2023-01-01', periods=100)
        self.data = pd.DataFrame({
            'target': np.random.randn(100),
            'feature1': np.random.randn(100),
            'feature2': np.random.randn(100),
        }, index=dates)

    def test_pit_safety_pass(self):
        dates = pd.date_range('2023-01-01', periods=10)
        predictions = pd.DataFrame({'pred': [1]*10}, index=dates)
        features = pd.DataFrame({
            'available_at': dates - pd.Timedelta(hours=1)
        }, index=dates)
        self.assertTrue(self.validator.check_pit_safety(predictions, features))

    def test_pit_safety_fail(self):
        dates = pd.date_range('2023-01-01', periods=10)
        predictions = pd.DataFrame({'pred': [1]*10}, index=dates)
        features = pd.DataFrame({
            'available_at': dates + pd.Timedelta(hours=1)
        }, index=dates)
        self.assertFalse(self.validator.check_pit_safety(predictions, features))

    def test_pit_safety_fallback(self):
        dates = pd.date_range('2023-01-01', periods=10)
        predictions = pd.DataFrame({'pred': [1]*10}, index=dates)
        features = pd.DataFrame({'f1': [1]*10}, index=dates)
        # Without available_at, returns True if monotonic
        self.assertTrue(self.validator.check_pit_safety(predictions, features))

    def test_leakage_detected_correlation(self):
        data = self.data.copy()
        # High correlation feature
        data['feature_leaky'] = data['target'] * 0.99
        self.assertTrue(self.validator.detect_leakage(data, ['feature_leaky']))

    def test_leakage_not_detected(self):
        self.assertFalse(self.validator.detect_leakage(self.data, ['feature1', 'feature2']))

    def test_leakage_detected_non_monotonic(self):
        data = self.data.copy()
        data = data.sample(frac=1.0) # Shuffle
        self.assertTrue(self.validator.detect_leakage(data, ['feature1']))

    def test_embargo_pass(self):
        t1 = pd.Timestamp('2023-01-01')
        t2 = pd.Timestamp('2023-01-04')
        self.assertTrue(self.validator.check_embargo(t1, t2))

    def test_embargo_fail(self):
        t1 = pd.Timestamp('2023-01-01')
        t2 = pd.Timestamp('2023-01-02')
        self.assertFalse(self.validator.check_embargo(t1, t2))

    def test_walk_forward_splits(self):
        splits = self.validator.walk_forward_validation(self.data, n_splits=5)
        self.assertEqual(len(splits), 5)
        for train, val in splits:
            self.assertTrue(len(train) > 0)
            self.assertTrue(len(val) > 0)
            self.assertTrue(val.index[0] > train.index[-1] + pd.Timedelta(days=1))

    def test_calculate_metrics(self):
        y_true = pd.Series([0.01, -0.01, 0.02, -0.01, 0.01])
        y_pred = pd.Series([1, -1, 1, -1, 1])
        metrics = self.validator.calculate_metrics(y_true, y_pred)
        self.assertGreater(metrics['ic'], 0.5)
        self.assertGreater(metrics['sharpe'], 0)

    def test_calculate_metrics_zero_std(self):
        y_true = pd.Series([1, 1, 1, 1])
        y_pred = pd.Series([1, 1, 1, 1])
        metrics = self.validator.calculate_metrics(y_true, y_pred)
        self.assertEqual(metrics['ic'], 0.0)
        self.assertEqual(metrics['sharpe'], 0.0)

    def test_validate_performance_pass(self):
        metrics = {'ic': 0.15, 'sharpe': 2.0}
        self.assertTrue(self.validator.validate_performance(metrics))

    def test_validate_performance_fail_ic(self):
        metrics = {'ic': 0.05, 'sharpe': 2.0}
        self.assertFalse(self.validator.validate_performance(metrics))

    def test_validate_performance_fail_sharpe(self):
        metrics = {'ic': 0.15, 'sharpe': 1.0}
        self.assertFalse(self.validator.validate_performance(metrics))

    def test_statistical_significance(self):
        y_true = pd.Series(np.random.randn(100))
        y_pred = y_true * 0.5 + np.random.randn(100) * 0.5
        results = self.validator.statistical_significance(y_true, y_pred, n_bootstraps=100)
        self.assertIn('p_value', results)
        self.assertIn('ic_mean', results)
        self.assertTrue(results['p_value'] < 0.05)

    def test_statistical_significance_noisy(self):
        y_true = pd.Series(np.random.randn(100))
        y_pred = pd.Series(np.random.randn(100))
        results = self.validator.statistical_significance(y_true, y_pred, n_bootstraps=100)
        self.assertTrue(results['p_value'] > 0.05 or results['ic_mean'] < 0.2)

if __name__ == '__main__':
    unittest.main()
