# omega.data package

# Auto-wired submodules and subpackages
try:
    from . import calendar
except ImportError:
    pass

try:
    from . import corporate_action
except ImportError:
    pass

try:
    from . import data_quality
except ImportError:
    pass

try:
    from . import data_validator
except ImportError:
    pass

try:
    from . import datasource_config
except ImportError:
    pass

try:
    from . import deployment_flow
except ImportError:
    pass

try:
    from . import live_ingestor
except ImportError:
    pass

try:
    from . import loader
except ImportError:
    pass

try:
    from . import market_flow
except ImportError:
    pass

try:
    from . import news_aggregator
except ImportError:
    pass

try:
    from . import production_data_pipeline
except ImportError:
    pass

try:
    from . import registry
except ImportError:
    pass

try:
    from . import sanitizer
except ImportError:
    pass

try:
    from . import validator
except ImportError:
    pass

try:
    from . import vci_bridge
except ImportError:
    pass

try:
    from . import vnstock_client
except ImportError:
    pass

try:
    from . import vnstock_adapter
except ImportError:
    pass

try:
    from . import vnstock_ingest
except ImportError:
    pass

try:
    from . import vnstock_live
except ImportError:
    pass

try:
    from . import vnstock_vci
except ImportError:
    pass

try:
    from . import vnd_price_contract
except ImportError:
    pass

try:
    from . import exchange_resolver
except ImportError:
    pass

try:
    from . import pipeline
except ImportError:
    pass

# Explicit re-exports for test collection and public API
try:
    from .sanitizer import DataSanitizer
except ImportError:
    pass
