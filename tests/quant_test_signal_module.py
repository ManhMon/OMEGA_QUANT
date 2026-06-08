import pytest

from omega.quant.signal_module import SignalModule, SignalModuleConfig


class TestSignalModule:
    def test_config_validation_top_percent_invalid(self):
        with pytest.raises(ValueError, match="invalid_threshold.*top_percent"):
            SignalModule(SignalModuleConfig(top_percent=1.5))

    def test_config_validation_bottom_percent_invalid(self):
        with pytest.raises(ValueError, match="invalid_threshold.*bottom_percent"):
            SignalModule(SignalModuleConfig(bottom_percent=-0.1))

    def test_config_validation_sum_exceeds_one(self):
        with pytest.raises(ValueError, match="invalid_threshold.*top_percent.*bottom_percent"):
            SignalModule(SignalModuleConfig(top_percent=0.6, bottom_percent=0.5))

    def test_input_validation_not_dict(self):
        module = SignalModule()
        with pytest.raises(TypeError, match="ScoreVector must be a dict"):
            module.transform([])

    def test_input_validation_wrong_type(self):
        module = SignalModule()
        with pytest.raises(ValueError, match="Input type must be ScoreVector"):
            module.transform({"type": "WrongType"})

    def test_input_validation_missing_fields(self):
        module = SignalModule()
        with pytest.raises(ValueError, match="Missing index/data"):
            module.transform({"type": "ScoreVector"})

    def test_basic_ranking_buy_sell_hold(self):
        module = SignalModule(SignalModuleConfig(top_percent=0.33, bottom_percent=0.33))
        score_vector = {
            "type": "ScoreVector",
            "index": {"timestamp": [1, 1, 1], "symbol": ["AAA", "BBB", "CCC"]},
            "data": {
                "AAA": {1: {"score": 10.0}},
                "BBB": {1: {"score": 5.0}},
                "CCC": {1: {"score": -1.0}},
            },
        }

        result = module.transform(score_vector)

        assert result["type"] == "SignalVector"
        assert result["data"]["AAA"][1]["signal"] == "BUY"
        assert result["data"]["BBB"][1]["signal"] == "HOLD"
        assert result["data"]["CCC"][1]["signal"] == "SELL"

    def test_limit_lock_forces_hold(self):
        module = SignalModule()
        score_vector = {
            "type": "ScoreVector",
            "index": {"timestamp": [1, 1], "symbol": ["AAA", "BBB"]},
            "data": {
                "AAA": {1: {"score": 100.0, "limit_lock": True}},
                "BBB": {1: {"score": -100.0}},
            },
        }

        result = module.transform(score_vector)

        assert result["data"]["AAA"][1]["signal"] == "HOLD"
        assert result["data"]["BBB"][1]["signal"] == "SELL"

    def test_nan_inf_masking(self):
        module = SignalModule()
        score_vector = {
            "type": "ScoreVector",
            "index": {"timestamp": [1, 1, 1], "symbol": ["AAA", "BBB", "CCC"]},
            "data": {
                "AAA": {1: {"score": float("nan")}},
                "BBB": {1: {"score": float("inf")}},
                "CCC": {1: {"score": 10.0}},
            },
        }

        result = module.transform(score_vector)

        assert result["data"]["AAA"][1]["signal"] == "HOLD"
        assert result["data"]["BBB"][1]["signal"] == "HOLD"
        assert result["data"]["CCC"][1]["signal"] == "BUY"

    def test_neutral_zone_enforcement(self):
        module = SignalModule(SignalModuleConfig(neutral_zone=5.0))
        score_vector = {
            "type": "ScoreVector",
            "index": {"timestamp": [1, 1, 1], "symbol": ["AAA", "BBB", "CCC"]},
            "data": {
                "AAA": {1: {"score": 10.0}},
                "BBB": {1: {"score": 3.0}},
                "CCC": {1: {"score": -10.0}},
            },
        }

        result = module.transform(score_vector)

        assert result["data"]["AAA"][1]["signal"] == "BUY"
        assert result["data"]["BBB"][1]["signal"] == "HOLD"
        assert result["data"]["CCC"][1]["signal"] == "SELL"

    def test_score_threshold_filtering(self):
        module = SignalModule(SignalModuleConfig(score_threshold=5.0))
        score_vector = {
            "type": "ScoreVector",
            "index": {"timestamp": [1, 1, 1], "symbol": ["AAA", "BBB", "CCC"]},
            "data": {
                "AAA": {1: {"score": 10.0}},
                "BBB": {1: {"score": 3.0}},
                "CCC": {1: {"score": -10.0}},
            },
        }

        result = module.transform(score_vector)

        assert result["data"]["AAA"][1]["signal"] == "BUY"
        assert result["data"]["BBB"][1]["signal"] == "HOLD"
        assert result["data"]["CCC"][1]["signal"] == "SELL"

    def test_degenerate_ranking_all_equal(self):
        module = SignalModule()
        score_vector = {
            "type": "ScoreVector",
            "index": {"timestamp": [1, 1, 1], "symbol": ["AAA", "BBB", "CCC"]},
            "data": {
                "AAA": {1: {"score": 5.0}},
                "BBB": {1: {"score": 5.0}},
                "CCC": {1: {"score": 5.0}},
            },
        }

        result = module.transform(score_vector)

        assert result["data"]["AAA"][1]["signal"] == "HOLD"
        assert result["data"]["BBB"][1]["signal"] == "HOLD"
        assert result["data"]["CCC"][1]["signal"] == "HOLD"

    def test_empty_scores_timestamp(self):
        module = SignalModule()
        score_vector = {
            "type": "ScoreVector",
            "index": {"timestamp": [1], "symbol": ["AAA"]},
            "data": {"AAA": {}},
        }

        result = module.transform(score_vector)

        assert result["type"] == "SignalVector"
        assert result["data"]["AAA"] == {}

    def test_contract_hash_present(self):
        module = SignalModule()
        assert hasattr(module, "CONTRACT_HASH")
        assert len(module.CONTRACT_HASH) == 64
