"""
OMEGA_QUANT Order Router (Layer 03)
Phase 4.3 / Phase 16: Order Routing, Latency Simulation & Liquidation Exposure

Routes orders between paper/live trading modes with robust fallback mechanisms,
configurable latency simulation, and per-symbol liquidation exposure tracking.

Author: Backend Engineer (Role 09)
Date: 2026-05-24
Version: 1.2.0
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Any

from .broker_gateway import (
    BrokerGateway,
    BrokerOrder,
    BrokerOrderResponse,
    BrokerOrderStatus,
    BrokerCredentials,
    PaperTradingEngine,
    OrderStatus,
    OrderSide,
)

logger = logging.getLogger(__name__)


@dataclass
class LatencyConfig:
    """
    Configurable latency simulation for order routing.

    Paper mode uses low base latency (local simulation).
    Live mode uses higher base latency (network + broker round-trip).
    Jitter is sampled from a Gaussian distribution (std_ms).
    Set rng_seed for deterministic behaviour in tests.
    """
    paper_base_ms: float = 2.0    # Base latency for paper mode (ms)
    paper_std_ms: float = 0.5     # Jitter std-dev for paper mode (ms)
    live_base_ms: float = 50.0    # Base latency for live mode (ms)
    live_std_ms: float = 10.0     # Jitter std-dev for live mode (ms)
    rng_seed: Optional[int] = None  # None = non-deterministic


@dataclass
class LiquidationExposure:
    """
    Per-symbol liquidation exposure snapshot.

    Tracks whether a symbol is in active liquidation (target_qty == 0),
    the remaining quantity to liquidate, and the notional value at last price.
    Updated on every submit_order call that carries a liquidation flag.
    """
    symbol: str
    is_liquidating: bool = False       # True when target_qty == 0 and position open
    remaining_qty: int = 0             # Shares still to be sold
    notional_value: float = 0.0        # remaining_qty * last_known_price
    gross_exposure: float = 0.0        # Absolute notional across all open liquidations
    submitted_qty: int = 0             # Cumulative qty submitted for this liquidation


class TradingMode(Enum):
    """Trading mode enumeration."""
    PAPER = "PAPER"  # Paper trading (simulation)
    LIVE = "LIVE"    # Live trading with real broker


class SSIBrokerGateway(BrokerGateway):
    """
    SSI Broker Gateway (simulated).
    
    Real implementation would connect to SSI's API.
    For now, simulates authentication and order submission.
    """
    
    def __init__(self, credentials: BrokerCredentials):
        """Initialize SSI Broker Gateway."""
        super().__init__(credentials)
        self._session_token: Optional[str] = None
    
    def authenticate(self) -> bool:
        """Authenticate with SSI API."""
        logger.info("Authenticating with SSI Broker API...")
        # Simulate authentication
        if self.credentials.api_key and self.credentials.api_secret:
            self._session_token = f"SSI_TOKEN_{self.credentials.account_id}"
            self.authenticated = True
            logger.info("SSI authentication successful")
            return True
        return False
    
    def submit_order(self, order: BrokerOrder) -> BrokerOrderResponse:
        """Submit order to SSI."""
        if not self.authenticated:
            # Attempt lazy authentication
            if not self.authenticate():
                return BrokerOrderResponse(
                    success=False,
                    status=OrderStatus.REJECTED,
                    error_code="NOT_AUTHENTICATED",
                    message="Broker not authenticated"
                )
        
        # Simulate order submission
        import time
        broker_order_id = f"SSI_{int(time.time() * 1000)}"
        
        logger.info(f"SSI order submitted: {broker_order_id} - {order.symbol} "
                   f"{order.side.value} {order.quantity}")
        
        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            client_order_id=order.client_order_id,
            status=OrderStatus.SUBMITTED,
            message="Order submitted to SSI",
        )
    
    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        """Get order status from SSI."""
        # Simulate status lookup
        return BrokerOrderStatus(
            broker_order_id=broker_order_id,
            client_order_id="",
            symbol="",
            side=OrderSide.BUY,
            status=OrderStatus.SUBMITTED,
            quantity=100,
            filled_quantity=0,
            remaining_quantity=100,
        )
    
    def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel order with SSI."""
        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            status=OrderStatus.CANCELLED,
            message="Order cancelled with SSI"
        )


@dataclass
class OrderRouterConfig:
    """Configuration for OrderRouter."""
    mode: TradingMode = TradingMode.PAPER
    ssi_credentials: Optional[BrokerCredentials] = None
    fallback_to_paper: bool = True          # Enable fallback on live failure
    latency_config: LatencyConfig = field(default_factory=LatencyConfig)
    simulate_latency: bool = True           # Set False to skip sleep in tests


class OrderRouter:
    """
    Routes orders between paper and live trading modes.

    Features:
    - Automatic routing based on trading mode
    - Supports SSI broker integration
    - Paper trading for simulation/testing
    - Robust fallback mechanism to paper trading on live gateway failure
    - Configurable latency simulation (paper: ~2 ms, live: ~50 ms + jitter)
    - Per-symbol liquidation exposure tracking (V21 defense concepts)
    """

    def __init__(self, config: OrderRouterConfig):
        """
        Initialize OrderRouter.

        Args:
            config: Router configuration
        """
        self.config = config
        self.mode = config.mode

        # Initialize volume profile configuration for POV routing
        self.volume_profile_enabled = True
        self.minimum_lot_size = 100  # Standard minimum lot size
        self.historical_volume_profiles: Dict[str, list] = {
            # Dummy historical volume profile logic
            "VNM": [0.05, 0.1, 0.15, 0.2, 0.15, 0.15, 0.1, 0.1],  # Example 8 periods
            "SSI": [0.1, 0.1, 0.1, 0.2, 0.2, 0.1, 0.1, 0.1],
        }

        # Initialize engines
        self.paper_engine = PaperTradingEngine()

        if config.mode == TradingMode.LIVE and config.ssi_credentials:
            self.ssi_gateway = SSIBrokerGateway(config.ssi_credentials)
        else:
            self.ssi_gateway = None

        self._current_gateway: BrokerGateway = self.paper_engine
        self._switch_mode(config.mode)

        # Latency simulation RNG — seeded for determinism when rng_seed is set
        lc = config.latency_config
        self._rng = random.Random(lc.rng_seed)

        # Liquidation exposure registry: symbol -> LiquidationExposure
        self.liquidation_exposure: Dict[str, LiquidationExposure] = {}

        # Explicit gateway provenance map: broker_order_id -> gateway name ("PAPER" | "SSI")
        # Replaces the fragile startswith("PAPER_") heuristic.
        self._order_gateway_map: Dict[str, str] = {}

        # Cumulative latency stats (ms)
        self._latency_samples: list = []

        logger.info(f"Initialized OrderRouter in {self.mode.value} mode")
    
    # ------------------------------------------------------------------
    # Latency simulation
    # ------------------------------------------------------------------

    def _simulate_latency(self) -> float:
        """
        Simulate routing latency and return the sampled value in ms.

        Paper mode: Gaussian(paper_base_ms, paper_std_ms), clipped to >= 0.
        Live mode:  Gaussian(live_base_ms,  live_std_ms),  clipped to >= 0.
        When simulate_latency=False the call is a no-op (returns 0.0).
        """
        if not self.config.simulate_latency:
            return 0.0

        lc = self.config.latency_config
        if self.mode == TradingMode.PAPER:
            base, std = lc.paper_base_ms, lc.paper_std_ms
        else:
            base, std = lc.live_base_ms, lc.live_std_ms

        sampled_ms = max(0.0, self._rng.gauss(base, std))
        time.sleep(sampled_ms / 1000.0)
        self._latency_samples.append(sampled_ms)
        logger.debug(f"Simulated latency: {sampled_ms:.2f} ms ({self.mode.value})")
        return sampled_ms

    def get_average_latency_ms(self) -> float:
        """Return mean simulated latency across all submissions (ms)."""
        if not self._latency_samples:
            return 0.0
        return sum(self._latency_samples) / len(self._latency_samples)

    # ------------------------------------------------------------------
    # Liquidation exposure tracking (V21 defense concepts)
    # ------------------------------------------------------------------

    def update_liquidation_exposure(
        self,
        symbol: str,
        is_liquidating: bool,
        remaining_qty: int,
        current_price: float,
        submitted_qty: int = 0,
    ) -> LiquidationExposure:
        """
        Register or update the liquidation exposure for a symbol.

        Called by ExecutionEngine before routing a liquidation order so the
        router has a live view of total gross exposure under liquidation.

        Args:
            symbol: Ticker being liquidated.
            is_liquidating: True when target_qty == 0 and position is open.
            remaining_qty: Shares still to be sold (after this submission).
            current_price: Last known price for notional calculation.
            submitted_qty: Qty being submitted in this batch.

        Returns:
            Updated LiquidationExposure snapshot.
        """
        notional = remaining_qty * current_price if current_price > 0 else 0.0

        exposure = self.liquidation_exposure.get(symbol)
        if exposure is None:
            exposure = LiquidationExposure(symbol=symbol)
            self.liquidation_exposure[symbol] = exposure

        exposure.is_liquidating = is_liquidating
        exposure.remaining_qty = remaining_qty
        exposure.notional_value = notional
        exposure.submitted_qty += submitted_qty

        # Recompute aggregate gross exposure across all active liquidations
        gross = sum(
            e.notional_value
            for e in self.liquidation_exposure.values()
            if e.is_liquidating
        )
        for e in self.liquidation_exposure.values():
            e.gross_exposure = gross

        logger.info(
            f"LiquidationExposure updated: {symbol} remaining={remaining_qty} "
            f"notional={notional:,.0f} gross_total={gross:,.0f}"
        )
        return exposure

    def get_liquidation_exposure(self, symbol: str) -> Optional[LiquidationExposure]:
        """Return current liquidation exposure for a symbol, or None."""
        return self.liquidation_exposure.get(symbol)

    def get_total_gross_liquidation_exposure(self) -> float:
        """Return total gross notional across all symbols under active liquidation."""
        return sum(
            e.notional_value
            for e in self.liquidation_exposure.values()
            if e.is_liquidating
        )

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _switch_mode(self, mode: TradingMode) -> None:
        """Switch trading mode internally."""
        if mode == TradingMode.PAPER:
            self._current_gateway = self.paper_engine
            logger.info("Switched to PAPER trading mode")
        elif mode == TradingMode.LIVE:
            if self.ssi_gateway:
                self._current_gateway = self.ssi_gateway
                logger.info("Switched to LIVE trading mode")
            elif self.config.ssi_credentials:
                # Lazy init SSI gateway if credentials provided but mode was PAPER
                self.ssi_gateway = SSIBrokerGateway(self.config.ssi_credentials)
                self._current_gateway = self.ssi_gateway
                logger.info("Switched to LIVE trading mode (lazy init)")
            else:
                logger.warning("LIVE mode requested but no SSI credentials. Using PAPER.")
                self.mode = TradingMode.PAPER
                self._current_gateway = self.paper_engine
    
    def switch_mode(self, mode: TradingMode) -> None:
        """Public method to switch trading mode.

        Updates both self.mode and config.mode so they stay in sync.
        If LIVE is requested but no credentials are available, _switch_mode
        silently falls back to PAPER and corrects self.mode; config.mode is
        then set to match the resolved mode.
        """
        self.mode = mode
        self._switch_mode(mode)
        # Sync config.mode to the resolved mode (may differ if fallback occurred)
        self.config.mode = self.mode
    
    def submit_order(
        self,
        order: BrokerOrder,
        current_price: Optional[float] = None
    ) -> BrokerOrderResponse:
        """
        Submit order through current gateway with fallback mechanism.
        
        Args:
            order: Order to submit
            current_price: Current market price (for paper trading/fallback)
            
        Returns:
            Response from broker
        """
        # --- Advanced Routing: POV (Percentage of Volume) ---
        if self.volume_profile_enabled and order.quantity >= self.minimum_lot_size * 10:
            logger.info(f"Applying POV routing for {order.symbol} size {order.quantity}")
            # Placeholder for POV routing logic: just log that we are splitting the order
            # In a real implementation, we would return a composite response or submit the first chunk
            profile = self.historical_volume_profiles.get(order.symbol, [0.1] * 10)
            target_chunk = int(order.quantity * profile[0])
            # Adjust to minimum lot size
            target_chunk = max(self.minimum_lot_size, (target_chunk // self.minimum_lot_size) * self.minimum_lot_size)
            logger.info(f"POV routing chunk size calculated: {target_chunk}")
            
            # For the scope of this update, we just modify the current order object
            # to submit the first chunk, and leave remaining logic for a full POV execution engine
            original_quantity = order.quantity
            order.quantity = target_chunk
            logger.info(f"Modifying initial submission size to {target_chunk} from {original_quantity} based on POV")

        # Simulate routing latency (paper ~2 ms, live ~50 ms + jitter)
        self._simulate_latency()

        logger.info(f"Routing order: {order.symbol} {order.side.value} {order.quantity} "
                   f"via {self.mode.value} mode")
        
        if self.mode == TradingMode.PAPER:
            if current_price is None:
                logger.error("Paper trading requires current_price parameter")
                return BrokerOrderResponse(
                    success=False,
                    client_order_id=order.client_order_id,
                    status=OrderStatus.REJECTED,
                    message="Paper trading requires current_price",
                    error_code="MISSING_PRICE",
                )
            response = self.paper_engine.submit_order(order, current_price)
            if response.success and response.broker_order_id:
                self._order_gateway_map[response.broker_order_id] = "PAPER"
            return response

        # LIVE Mode
        try:
            # Validate gateway
            if self.ssi_gateway is None:
                raise ValueError("LIVE mode active but no live gateway configured")

            # Authenticate if needed
            if not self.ssi_gateway.authenticated:
                if not self.ssi_gateway.authenticate():
                    raise ConnectionError("SSI Broker authentication failed")

            # Submit order
            response = self.ssi_gateway.submit_order(order)
            if not response.success:
                raise RuntimeError(f"SSI Order submission rejected: {response.message}")

            if response.broker_order_id:
                self._order_gateway_map[response.broker_order_id] = "SSI"
            return response

        except Exception as e:
            logger.error(f"Live order submission failed: {e}")
            if self.config.fallback_to_paper:
                logger.warning("Attempting graceful fallback to PAPER trading mode...")
                if current_price is not None:
                    fallback_response = self.paper_engine.submit_order(order, current_price)
                    fallback_response.message = f"FALLBACK ACTIVE: {fallback_response.message} (Reason: {e})"
                    if fallback_response.success and fallback_response.broker_order_id:
                        self._order_gateway_map[fallback_response.broker_order_id] = "PAPER"
                    return fallback_response
                else:
                    logger.error("Fallback failed: No current price available for paper execution")
                    return BrokerOrderResponse(
                        success=False,
                        client_order_id=order.client_order_id,
                        status=OrderStatus.REJECTED,
                        message=f"Live submission failed and fallback price missing: {e}",
                        error_code="FALLBACK_FAILED_NO_PRICE",
                    )
            else:
                return BrokerOrderResponse(
                    success=False,
                    client_order_id=order.client_order_id,
                    status=OrderStatus.REJECTED,
                    message=f"Live submission failed: {e}",
                    error_code="LIVE_SUBMISSION_FAILED",
                )
    
    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        """Get order status from the gateway that submitted this order.

        Uses explicit provenance map (_order_gateway_map) recorded at submission
        time.  Falls back to current gateway when the order is unknown (e.g.
        orders submitted before this session started).
        """
        provenance = self._order_gateway_map.get(broker_order_id)
        if provenance == "PAPER":
            return self.paper_engine.get_order_status(broker_order_id)
        elif provenance == "SSI":
            if self.ssi_gateway is None:
                raise ValueError(f"SSI gateway not configured for order: {broker_order_id}")
            return self.ssi_gateway.get_order_status(broker_order_id)
        else:
            # Unknown provenance — fall back to current gateway
            if self.mode == TradingMode.PAPER:
                return self.paper_engine.get_order_status(broker_order_id)
            elif self.ssi_gateway:
                return self.ssi_gateway.get_order_status(broker_order_id)
            else:
                raise ValueError(f"Cannot determine execution gateway for order: {broker_order_id}")

    def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel order through the gateway that submitted it.

        Uses explicit provenance map (_order_gateway_map) recorded at submission
        time.  Falls back to current gateway when the order is unknown.
        """
        provenance = self._order_gateway_map.get(broker_order_id)
        if provenance == "PAPER":
            return self.paper_engine.cancel_order(broker_order_id)
        elif provenance == "SSI":
            if self.ssi_gateway is None:
                return BrokerOrderResponse(
                    success=False,
                    broker_order_id=broker_order_id,
                    status=OrderStatus.REJECTED,
                    message="SSI gateway not configured",
                    error_code="INVALID_ORDER_ID",
                )
            return self.ssi_gateway.cancel_order(broker_order_id)
        else:
            # Unknown provenance — fall back to current gateway
            if self.mode == TradingMode.PAPER:
                return self.paper_engine.cancel_order(broker_order_id)
            elif self.ssi_gateway:
                return self.ssi_gateway.cancel_order(broker_order_id)
            else:
                return BrokerOrderResponse(
                    success=False,
                    broker_order_id=broker_order_id,
                    status=OrderStatus.REJECTED,
                    message=f"Cannot determine execution gateway for order: {broker_order_id}",
                    error_code="INVALID_ORDER_ID",
                )
    
    def authenticate(self) -> bool:
        """Authenticate current gateway."""
        if self.mode == TradingMode.LIVE and self.ssi_gateway:
            return self.ssi_gateway.authenticate()
        return True  # Paper trading always authenticated
