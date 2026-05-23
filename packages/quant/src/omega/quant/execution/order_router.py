"""
OMEGA_QUANT Execution Module - Order Router
Phase 4.3: Order Routing & Broker Integration

Author: Backend Engineer (Role 09)
Date: 2026-05-14
Version: 1.0.0
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import uuid

from omega.quant.execution.broker_gateway import (
    BrokerOrder,
    BrokerCredentials,
    OrderResponse,
    OrderStatus,
    PaperTradingEngine
)


class TradingMode(Enum):
    """Trading mode enumeration."""
    PAPER = "PAPER"
    LIVE = "LIVE"


@dataclass
class OrderRouterConfig:
    """
    Order router configuration.
    
    Attributes:
        mode: Trading mode (PAPER or LIVE)
        ssi_credentials: SSI broker credentials (required for LIVE mode)
    """
    mode: TradingMode
    ssi_credentials: Optional[BrokerCredentials] = None


class SSIBrokerGateway:
    """
    SSI Broker Gateway - Mock implementation.
    
    In production, this would connect to SSI's actual API.
    For testing, this simulates SSI order submission.
    """
    
    def __init__(self, credentials: BrokerCredentials):
        """
        Initialize SSI broker gateway.
        
        Args:
            credentials: SSI broker credentials
        """
        self.credentials = credentials
        self._authenticated = False
    
    def authenticate(self) -> bool:
        """
        Authenticate with SSI broker.
        
        Returns:
            True if authentication successful
        """
        # Mock authentication - always succeeds
        self._authenticated = True
        return True
    
    def submit_order(self, order: BrokerOrder) -> OrderResponse:
        """
        Submit order to SSI broker.
        
        Args:
            order: BrokerOrder to submit
        
        Returns:
            OrderResponse from SSI
        """
        if not self._authenticated:
            return OrderResponse(
                success=False,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                message="Not authenticated"
            )
        
        # Generate SSI order ID
        order_id = f"SSI_{uuid.uuid4().hex[:8].upper()}"
        
        # Mock successful submission
        return OrderResponse(
            success=True,
            broker_order_id=order_id,
            status=OrderStatus.SUBMITTED,
            message="Order submitted to SSI"
        )


class OrderRouter:
    """
    Order Router - Routes orders to appropriate execution venue.
    
    Supports:
    - PAPER mode: Routes to PaperTradingEngine
    - LIVE mode: Routes to SSIBrokerGateway
    
    Can switch between modes dynamically.
    """
    
    def __init__(self, config: OrderRouterConfig):
        """
        Initialize order router.
        
        Args:
            config: OrderRouterConfig with mode and credentials
        """
        self.config = config
        self.mode = config.mode
        
        # Initialize engines
        self._paper_engine = PaperTradingEngine()
        
        if config.ssi_credentials:
            self._ssi_gateway = SSIBrokerGateway(config.ssi_credentials)
        else:
            self._ssi_gateway = None
    
    def authenticate(self) -> bool:
        """
        Authenticate with broker (LIVE mode only).
        
        Returns:
            True if authentication successful
        """
        if self.mode == TradingMode.LIVE:
            if self._ssi_gateway is None:
                raise ValueError("SSI credentials not provided")
            return self._ssi_gateway.authenticate()
        
        # Paper mode doesn't need authentication
        return True
    
    def submit_order(
        self,
        order: BrokerOrder,
        current_price: Optional[float] = None
    ) -> OrderResponse:
        """
        Submit order to appropriate execution venue.
        
        Args:
            order: BrokerOrder to submit
            current_price: Current market price (required for PAPER mode)
        
        Returns:
            OrderResponse from execution venue
        """
        if self.mode == TradingMode.PAPER:
            if current_price is None:
                raise ValueError("current_price required for PAPER mode")
            return self._paper_engine.submit_order(order, current_price)
        
        elif self.mode == TradingMode.LIVE:
            if self._ssi_gateway is None:
                raise ValueError("SSI credentials not provided")
            return self._ssi_gateway.submit_order(order)
        
        else:
            raise ValueError(f"Unknown trading mode: {self.mode}")
    
    def switch_mode(self, new_mode: TradingMode):
        """
        Switch trading mode and keep config.mode in sync.

        Args:
            new_mode: New trading mode to switch to
        """
        self.mode = new_mode
        self.config.mode = new_mode
