# omega.data package

# Active modules fail closed: internal import failures must remain visible.
from . import calendar, corporate_action, data_quality, data_validator
from . import datasource_config, deployment_flow, live_ingestor, loader
from . import market_flow, news_aggregator, production_data_pipeline, registry
from . import sanitizer, validator, vnstock_client, vnstock_vci
from . import vnd_price_contract, exchange_resolver, pipeline
from .sanitizer import DataSanitizer

# These modules intentionally raise ImportError because they are archived.
for _archived_name in ("vci_bridge", "vnstock_adapter", "vnstock_ingest"):
    try:
        __import__(f"{__name__}.{_archived_name}")
    except ImportError as exc:
        if "archived" not in str(exc).lower():
            raise
