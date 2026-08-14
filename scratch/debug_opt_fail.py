import sys
from pathlib import Path
import numpy as np
import pandas as pd
import traceback

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

import omega.quant.evolution.diverse_alpha_evolution as dae
import omega.quant.evolution.genetic_engine as ge
from omega.quant.evolution.diverse_alpha_evolution import (
    DiverseAlphaEvolution,
    DiverseEvolutionConfig,
    _candidate_from_genome_standard,
)
from omega.quant.evolution.genetic_alpha import Genome, Node

def run_debug():
    rows = 40
    dates = pd.to_datetime(np.tile(["2024-01-03", "2024-01-01", "2024-01-02", "2024-01-04"], rows // 4))
    tickers = np.tile(np.array(["BBB", "AAA", "AAA", "BBB", "AAA"]), rows // 5)
    frame = pd.DataFrame(
        {
            "date": dates,
            "ticker": tickers,
            "close": np.linspace(1.0, 2.1, rows),
            "open": np.linspace(1.0, 2.1, rows),
            "high": np.linspace(1.1, 2.2, rows),
            "low": np.linspace(0.9, 2.0, rows),
            "volume": np.linspace(1000.0, 2000.0, rows),
            "returns": np.linspace(-0.1, 0.1, rows),
            "target": np.linspace(-0.2, 0.2, rows),
        }
    )
    train_features, train_target = dae._build_standard_features(frame, "target", 3)
    val_features, val_target = dae._build_standard_features(frame, "target", 3)
    config = DiverseEvolutionConfig(neutralize_size_sector=False, min_observations=4)

    original_to_datetime = ge.pd.to_datetime
    original_lexsort = ge.np.lexsort
    calls = {"to_datetime": 0, "lexsort": 0}

    def fail_to_datetime(*args, **kwargs):
        calls["to_datetime"] += 1
        raise AssertionError("should use precomputed grouped ts structure (pd.to_datetime)")

    def fail_lexsort(*args, **kwargs):
        calls["lexsort"] += 1
        raise AssertionError("should use precomputed grouped ts structure (np.lexsort)")

    ge.pd.to_datetime = fail_to_datetime
    ge.np.lexsort = fail_lexsort

    try:
        # bypass try-except Exception in diverse_alpha_evolution to see the raw error
        gp_config = dae._build_standard_gp_config(config)
        ge.set_active_dataset_id(train_features.get("__dataset_id__") if train_features else None)
        ge.set_active_grouped_ts_structure(train_features.get("__grouped_ts_structure__") if train_features else None)
        
        print("Active grouped structure:", ge.get_active_grouped_ts_structure() is not None)
        
        tree, train_signal = dae._execute_standard_signal(Genome(tree=Node("std", [Node("close")])), train_features)
        print("Train signal std:", np.std(train_signal))
        individual = ge.GPIndividual(tree=tree)
        train_prepared = individual._prepare_alpha_series(train_features)
        print("Train prepared:", train_prepared is not None)
        if train_prepared is not None:
            train_alpha, train_valid_fraction = train_prepared
            train_score = individual._compute_combined_ic(
                train_alpha,
                train_target,
                train_features,
                gp_config,
            )
            print("Train score:", train_score)
        
        ge.set_active_dataset_id(val_features.get("__dataset_id__") if val_features else None)
        ge.set_active_grouped_ts_structure(val_features.get("__grouped_ts_structure__") if val_features else None)
        _, val_signal = dae._execute_standard_signal(Genome(tree=Node("std", [Node("close")])), val_features)
        print("Val signal std:", np.std(val_signal))
        val_prepared = individual._prepare_alpha_series(val_features)
        print("Val prepared:", val_prepared is not None)
        if val_prepared is not None:
            val_alpha, _ = val_prepared
            val_score = individual._compute_combined_ic(
                val_alpha,
                val_target,
                val_features,
                gp_config,
            )
            print("Val score:", val_score)
            
        candidate = _candidate_from_genome_standard(
            Genome(tree=Node("std", [Node("close")])),
            frame,
            frame,
            "target",
            config,
            train_features=train_features,
            train_target=train_target,
            val_features=val_features,
            val_target=val_target,
        )
        print("Candidate created:", candidate is not None)
        
    except Exception as e:
        print("Exception caught:")
        traceback.print_exc()
    finally:
        ge.pd.to_datetime = original_to_datetime
        ge.np.lexsort = original_lexsort
        ge.set_active_grouped_ts_structure(None)
        ge.set_active_dataset_id(None)

if __name__ == "__main__":
    run_debug()
