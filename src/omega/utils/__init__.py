

# Auto-wired submodules and subpackages
try:
    from . import logger
except ImportError:
    pass
