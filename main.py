#!/usr/bin/env python
"""Entry point for Release Notes Agent"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.cli import cli

if __name__ == '__main__':
    cli()
