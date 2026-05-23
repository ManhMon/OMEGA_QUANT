"""
OMEGA_QUANT Order Router (Layer 03)
Phase 4.3: Order Routing & Broker Integration

Routes orders between paper/live trading modes with robust fallback mechanisms.

Author: Backend Engineer (Role 09)
Date: 2026-05-18
Version: 1.1.0
"""

from __future__ import annotations

import logging
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
    fallback_to_paper: bool = True  # Enable fallback on live failure


class OrderRouter:
    """
    Routes orders between paper and live trading modes.
    
    Features:
    - Automatic routing based on trading mode
    - Supports SSI broker integration
    - Paper trading for simulation/testing
    - Robust fallback mechanism to paper trading on live gateway failure
    """
    
    def __init__(self, config: OrderRouterConfig):
        """
        Initialize OrderRouter.
        
        Args:
            config: Router configuration
        """
        self.config = config
        self.mode = config.mode
        
        # Initialize engines
        self.paper_engine = PaperTradingEngine()
        
        if config.mode == TradingMode.LIVE and config.ssi_credentials:
            self.ssi_gateway = SSIBrokerGateway(config.ssi_credentials)
        else:
            self.ssi_gateway = None
        
        self._current_gateway: BrokerGateway = self.paper_engine
        self._switch_mode(config.mode)
        
        logger.info(f"Initialized OrderRouter in {self.mode.value} mode")
    
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
        """Public method to switch trading mode."""
        self.mode = mode
        self._switch_mode(mode)
    
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
            return self.paper_engine.submit_order(order, current_price)
        
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
            
            return response
            
        except Exception as e:
            logger.error(f"Live order submission failed: {e}")
            if self.config.fallback_to_paper:
                logger.warning("Attempting graceful fallback to PAPER trading mode...")
                if current_price is not None:
                    # Temporary fallback
                    fallback_response = self.paper_engine.submit_order(order, current_price)
                    fallback_response.message = f"FALLBACK ACTIVE: {fallback_response.message} (Reason: {e})"
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
        """Get order status from current gateway."""
        if broker_order_id.startswith("PAPER_"):
            return self.paper_engine.get_order_status(broker_order_id)
        elif self.ssi_gateway:
            return self.ssi_gateway.get_order_status(broker_order_id)
        else:
            raise ValueError(f"Cannot determine execution gateway for order: {broker_order_id}")
    
    def cancel_order(self, broker_order_id: str) -> BrokerOrderResponse:
        """Cancel order through current gateway."""
        if broker_order_id.startswith("PAPER_"):
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
