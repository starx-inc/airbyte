#!/usr/bin/env python3

import sys

from airbyte_cdk.entrypoint import launch
from .source import SourceEcforce


def run():
    source = SourceEcforce()
    launch(source, sys.argv[1:])


if __name__ == "__main__":
    run()
