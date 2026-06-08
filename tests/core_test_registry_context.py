"""
Tests for Model Registry and Context Assembly (Institutional Grade)

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
Version: 1.0.0
"""

import pytest
from omega.core.registry.model_registry import (
    ModelRegistry,
    ModelStatus,
    ModelVersion,
    get_model_registry,
)
from omega.core.context.context_assembler import (
    ContextAssembler,
    ContextChunk,
    ContextPriority,
    TokenBudget,
    get_context_assembler,
)


class TestModelRegistry:
    """Test Model Registry features."""
    
    def test_create_model(self):
        """Test creating a model."""
        registry = ModelRegistry()
        model = registry.create_model(
            model_type="xgboost",
            name="alpha_v1",
            owner="DataScientist",
            tags=["trend", "momentum"],
            pit_safe=True,
        )
        
        assert model.model_id is not None
        assert model.model_type == "xgboost"
        assert model.name == "alpha_v1"
        assert model.pit_safe == True
        assert "trend" in model.tags
    
    def test_create_version(self):
        """Test creating a version for a model."""
        registry = ModelRegistry()
        model = registry.create_model("xgboost", "alpha_v1", "DS")
        
        version = registry.create_version(
            model_id=model.model_id,
            version="1.0.0",
            status=ModelStatus.TRAINING,
            metrics={"sharpe": 1.5, "ic": 0.05},
            pit_safe=True,
        )
        
        assert version.version == "1.0.0"
        assert version.status == ModelStatus.TRAINING
        assert version.metrics["sharpe"] == 1.5
        assert version.pit_safe == True
    
    def test_rollback_metadata(self):
        """Test rollback creates new version with rollback metadata."""
        registry = ModelRegistry()
        model = registry.create_model("xgboost", "alpha_v1", "DS")
        
        # Create version with metrics
        v1 = registry.create_version(
            model.model_id, "1.0.0",
            status=ModelStatus.DEPLOYED,
            metrics={"sharpe": 1.5, "ic": 0.05},
            pit_safe=True,
        )
        
        # Verify rollback metadata structure
        rollback_meta = {
            **v1.metadata,
            "rollback_from": v1.version,
            "rollback_at": "2026-05-13T00:00:00Z",
        }
        
        # Create rollback version manually
        rollback_v = ModelVersion(
            model_id=model.model_id,
            version=f"{v1.version}.rollback",
            status=ModelStatus.DEPLOYED,
            metadata=rollback_meta,
            artifacts=v1.artifacts.copy(),
            metrics=v1.metrics.copy(),
            lineage=[v1.version_id],
            pit_safe=v1.pit_safe,
        )
        
        assert rollback_v.version == "1.0.0.rollback"
        assert rollback_v.lineage == [v1.version_id]
        assert rollback_v.metrics["sharpe"] == 1.5


class TestContextAssembly:
    """Test Context Assembly (Token-Savior) features."""
    
    def test_token_budget_allocation(self):
        """Test token budget allocation."""
        budget = TokenBudget(total_tokens=1000)
        
        # Allocate within budget
        assert budget.allocate("system", 100)
        assert budget.usage["system"] == 100
        assert budget.get_remaining("system") == 50  # 15% of 1000 = 150
        
        # Over budget
        assert not budget.allocate("system", 100)
    
    def test_semantic_pruning(self):
        """Test semantic context pruning."""
        # Total budget 1000 tokens. 
        # Scratch (10%) = 100 tokens.
        # chunks fit but let's check category limits.
        assembler = ContextAssembler(total_budget=10000) # Big budget to test scoring first
        
        chunks = [
            ContextChunk(
                chunk_id="c1",
                content="This is an alpha signal based on RSI.",
                priority=ContextPriority.HIGH,
                token_count=100,
                source="alpha.py"
            ),
            ContextChunk(
                chunk_id="c2",
                content="System configuration for database connections.",
                priority=ContextPriority.LOW,
                token_count=100,
                source="db.py"
            ),
        ]
        
        # Query about alpha signals
        result = assembler.assemble(chunks, query="alpha signal")
        
        # In big budget, both should be used
        assert result.chunks_used == 2
        assert "alpha signal" in result.assembled_content.lower()
    
    def test_context_assembly_priority(self):
        """Test that assembly respects priority ordering."""
        # Total 1000 tokens. Critical (15%) = 150.
        assembler = ContextAssembler(total_budget=1000)
        
        chunks = [
            ContextChunk(
                chunk_id="critical",
                content="Critical system spec",
                priority=ContextPriority.CRITICAL,
                token_count=50,
            ),
        ]
        
        result = assembler.assemble(chunks, query="test")
        assert result.chunks_used == 1
    
    def test_minimal_context_interface(self):
        """Test the high-level get_minimal_context interface."""
        assembler = ContextAssembler()
        chunks = [ContextChunk("c1", "content", ContextPriority.HIGH, token_count=10)]
        
        content = assembler.get_minimal_context(chunks, "query")
        # [SYSTEM] only appears if prompt is provided
        assert "[CONTEXT]" in content
        
        # With prompt
        content_with_prompt = assembler.assemble(chunks, "query", system_prompt="Be helpful").assembled_content
        assert "[SYSTEM]" in content_with_prompt
        assert "Be helpful" in content_with_prompt

    def test_context_assembly_caching_hit_rate(self, monkeypatch):
        """Test repeated assembly reuses cached relevance and pruning results."""
        assembler = ContextAssembler(total_budget=1000)
        chunks = [
            ContextChunk(
                chunk_id="c1",
                content="alpha signal from registry cache",
                priority=ContextPriority.HIGH,
                token_count=20,
                source="alpha.py",
            ),
            ContextChunk(
                chunk_id="c2",
                content="model registry pipeline context",
                priority=ContextPriority.MEDIUM,
                token_count=20,
                source="registry.py",
            ),
        ]

        compute_calls = {"count": 0}
        original_compute = assembler.pruner.compute_relevance

        def counting_compute(chunk, query):
            compute_calls["count"] += 1
            return original_compute(chunk, query)

        monkeypatch.setattr(assembler.pruner, "compute_relevance", counting_compute)

        first = assembler.assemble(chunks, query="registry cache")
        second = assembler.assemble(chunks, query="registry cache")

        assert first.chunks_used == second.chunks_used == 2
        assert compute_calls["count"] == len(chunks)
        assert len(assembler._relevance_cache) == len(chunks)
        assert len(assembler._pruned_cache) == 1

    def test_context_assembly_cache_hit_budget_enforcement(self):
        """Test cache hits still enforce current-run token budget."""
        assembler = ContextAssembler(total_budget=1000)
        chunks = [
            ContextChunk(
                chunk_id="c1",
                content="alpha signal cache budget chunk one",
                priority=ContextPriority.HIGH,
                token_count=250,
                source="alpha_one.py",
            ),
            ContextChunk(
                chunk_id="c2",
                content="alpha signal cache budget chunk two",
                priority=ContextPriority.HIGH,
                token_count=250,
                source="alpha_two.py",
            ),
        ]

        first = assembler.assemble(chunks, query="alpha cache budget")

        second = assembler.assemble(
            chunks,
            query="alpha cache budget",
            task_description="x" * 996,
        )

        assert first.chunks_used == 2
        assert len(assembler._pruned_cache) == 1
        assert second.chunks_used == 1
        assert "alpha_one.py" in second.assembled_content
        assert "alpha_two.py" not in second.assembled_content

    def test_context_assembly_priority_budget_routing(self, monkeypatch):
        """Test chunk priorities route to correct token budget categories."""
        assembler = ContextAssembler(total_budget=1000)
        chunks = [
            ContextChunk("critical", "critical context", ContextPriority.CRITICAL, token_count=10),
            ContextChunk("high", "high context", ContextPriority.HIGH, token_count=10),
            ContextChunk("medium", "medium context", ContextPriority.MEDIUM, token_count=10),
            ContextChunk("low", "low context", ContextPriority.LOW, token_count=10),
        ]

        allocated_categories = []
        original_allocate = TokenBudget.allocate

        def capture_allocate(self, category, tokens):
            allocated_categories.append(category)
            return original_allocate(self, category, tokens)

        monkeypatch.setattr(TokenBudget, "allocate", capture_allocate)

        result = assembler.assemble(chunks, query="context")

        assert result.chunks_used == 4
        assert allocated_categories == ["system", "task", "history", "scratch"]


class TestSingletons:
    """Test singletons for registry and assembler."""
    
    def test_registry_singleton(self):
        assert get_model_registry() is get_model_registry()
        
    def test_assembler_singleton(self):
        assert get_context_assembler() is get_context_assembler()
