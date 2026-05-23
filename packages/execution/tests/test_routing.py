import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from omega.execution.routing import POVRoutingEngine, Order

def test_pov_routing_even_distribution():
    engine = POVRoutingEngine(min_lot_size=100)
    order = Order(symbol="SSI", quantity=600, side="BUY", target_pov=0.2)
    # Even distribution over 6 buckets
    engine.load_historical_profile("SSI", [1/6] * 6)
    
    # Very high historical volume so we aren't capped by POV
    chunks = engine.route_order(order, historical_daily_volume=1000000)
    
    assert len(chunks) == 6
    for chunk in chunks:
        assert chunk.quantity == 100
        assert chunk.symbol == "SSI"
        
def test_pov_routing_capped_by_volume():
    engine = POVRoutingEngine(min_lot_size=100)
    # Order wants 2000, but historical volume is low
    order = Order(symbol="SSI", quantity=2000, side="BUY", target_pov=0.1)
    engine.load_historical_profile("SSI", [0.5, 0.5])
    
    # Volume is 10,000. Bucket 1 = 5,000. POV=0.1 -> Max participate = 500
    chunks = engine.route_order(order, historical_daily_volume=10000)
    
    assert len(chunks) == 2
    assert chunks[0].quantity == 500
    assert chunks[1].quantity == 500
    # Total allocated is 1000, which is < 2000 target because of POV limit.

def test_pov_rounding_to_lot_size():
    engine = POVRoutingEngine(min_lot_size=100)
    order = Order(symbol="VND", quantity=350, side="SELL", target_pov=1.0)
    engine.load_historical_profile("VND", [0.4, 0.6]) # 140 and 210
    
    chunks = engine.route_order(order, historical_daily_volume=10000)
    # Bucket 0: 140 -> 100
    # Bucket 1: remaining is 250 -> 200
    assert chunks[0].quantity == 100
    assert chunks[1].quantity == 200

def test_zero_historical_volume():
    engine = POVRoutingEngine()
    order = Order(symbol="SSI", quantity=1000, side="BUY")
    with pytest.raises(ValueError):
        engine.route_order(order, historical_daily_volume=0)
