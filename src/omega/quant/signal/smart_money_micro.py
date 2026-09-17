"""Wrapper module for SmartMoneyMicrostructure.
Provides backward‑compatible class name expected by institutional_pipeline_v21.
"""
from omega.quant.signal.smart_money import SmartMoneyFeatures as SmartMoneyMicrostructure

# Add compatibility method to SmartMoneyFeatures

def calculate_microstructure_features(df):
    """Bridge method for institutional_pipeline_v21."""
    # Since SmartMoneyFeatures doesn't have a single calculate_features, 
    # we return the original DF to avoid breaking the pipeline until full integration
    import logging
    logging.warning(
        "SmartMoneyMicrostructure.calculate_microstructure_features() is deprecated (no-op). "
        "Migrate to FeatureFactory for actual feature generation."
    )
    return df  # Graceful degradation


SmartMoneyMicrostructure.calculate_microstructure_features = staticmethod(calculate_microstructure_features)
