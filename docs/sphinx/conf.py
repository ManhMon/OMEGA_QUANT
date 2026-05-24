# Sphinx documentation build configuration file

import os
import sys

sys.path.insert(0, os.path.abspath('../../packages/quant/src'))
sys.path.insert(0, os.path.abspath('../../packages/execution/src'))
sys.path.insert(0, os.path.abspath('../../packages/core/src'))

project = 'OMEGA_QUANT'
copyright = '2026, Ly & Engineering Team'
author = 'Role11-DevOps'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'alabaster'
html_static_path = ['_static']