    # ------------------------------------------------------------------
    # Implementation Shortfall (IS) Routing
    # ------------------------------------------------------------------
    def apply_is_routing(
        self, order: BrokerOrder, arrival_price: float, current_price: float, alpha_decay_rate: float
    ) -> int:
        """
        Implementation Shortfall (IS) routing algorithm.
        Dynamically adjusts participation rate based on alpha decay and price drift.

        Args:
            order: The broker order
            arrival_price: The price at the time the decision was made
            current_price: The current market price
            alpha_decay_rate: Estimated half-life decay of the alpha signal (0.0 to 1.0)

        Returns:
            int: The chunk size to execute in the current slice.
        """
        if order.quantity < self.minimum_lot_size * 2:
            return order.quantity

        # IS Logic: If price moves against us (shortfall), and alpha decays slowly, we slow down execution to save spread.
        # If alpha decays fast, we execute aggressively regardless of shortfall.
        drift = (current_price - arrival_price) / arrival_price
        if order.side.name == "SELL":
            drift = -drift  # Flip sign for sells: lower price = negative drift = adverse
            
        base_participation_rate = 0.10  # Base POV equivalent (10%)
        
        if drift < -0.01:
            # Adverse movement > 1%
            if alpha_decay_rate > 0.5:
                # Fast decay -> panic execute
                participation_rate = 0.30
            else:
                # Slow decay -> wait it out
                participation_rate = 0.05
        elif drift > 0.01:
            # Favorable movement > 1%
            participation_rate = 0.20
        else:
            # Flat
            participation_rate = base_participation_rate + (alpha_decay_rate * 0.10)

        chunk_size = int(order.quantity * participation_rate)
        
        # Round to board lot
        chunk_size = max(self.minimum_lot_size, (chunk_size // self.minimum_lot_size) * self.minimum_lot_size)
        return min(chunk_size, order.quantity)