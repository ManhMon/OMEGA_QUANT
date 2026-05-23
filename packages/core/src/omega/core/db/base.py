"""
Database Base Configuration
PIT-safe base classes and session management.

Version: 2.1
Compliance: V21_QUANT Institutional Grade
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import create_engine, Column, DateTime, String, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Base class for all models
Base = declarative_base()


class PITMixin:
    """
    Point-in-Time mixin for temporal queries.
    
    Ensures all data has proper temporal semantics:
    - as_of: When the data represents (business time)
    - available_at: When the data became available (system time)
    
    This prevents look-ahead bias in backtesting.
    
    Constraint: available_at >= as_of (data cannot be available before it exists)
    """
    
    as_of = Column(DateTime, nullable=False, index=True, 
                   comment="Business time - when this data represents")
    available_at = Column(DateTime, nullable=False, index=True,
                         comment="System time - when this data became available")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                       comment="Record creation timestamp")
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                       onupdate=lambda: datetime.now(timezone.utc),
                       comment="Record update timestamp")
    
    @declared_attr
    def __table_args__(cls):
        """Add PIT constraint to all tables using this mixin."""
        args = (
            CheckConstraint('available_at >= as_of', name=f'ck_{cls.__tablename__}_pit_safety'),
        )
        # Merge with any existing table args from the child class
        if hasattr(cls, '_table_args_'):
            existing = cls._table_args_
            if isinstance(existing, dict):
                return args + (existing,)
            elif isinstance(existing, tuple):
                return args + existing
        return args


class VersionedMixin:
    """
    Versioning mixin for reproducibility.
    
    All artifacts, models, and datasets must be versioned.
    """
    
    version = Column(String(64), nullable=False, index=True,
                    comment="Semantic version (e.g., 1.0.0)")
    checksum = Column(String(64), nullable=True,
                     comment="SHA256 checksum for integrity verification")


# Global engine and session factory
_engine = None
_SessionFactory = None


def get_engine(database_url: Optional[str] = None, **kwargs):
    """
    Get or create database engine.
    
    Args:
        database_url: SQLAlchemy database URL
        **kwargs: Additional engine configuration
        
    Returns:
        SQLAlchemy engine instance
    """
    global _engine
    
    if _engine is None:
        if database_url is None:
            # Default to SQLite in-memory for testing
            database_url = "sqlite:///:memory:"
            kwargs.setdefault("connect_args", {"check_same_thread": False})
            kwargs.setdefault("poolclass", StaticPool)
        
        _engine = create_engine(database_url, **kwargs)
    
    return _engine


def get_session(engine=None) -> Session:
    """
    Get database session.
    
    Args:
        engine: Optional engine instance
        
    Returns:
        SQLAlchemy session
    """
    global _SessionFactory
    
    if engine is None:
        engine = get_engine()
    
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=engine)
    
    return _SessionFactory()


def init_db(database_url: Optional[str] = None, drop_all: bool = False):
    """
    Initialize database schema.
    
    Args:
        database_url: SQLAlchemy database URL
        drop_all: If True, drop all tables before creating
        
    Returns:
        Engine instance
    """
    engine = get_engine(database_url)
    
    if drop_all:
        Base.metadata.drop_all(engine)
    
    Base.metadata.create_all(engine)
    
    return engine
