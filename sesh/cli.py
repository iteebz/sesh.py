import sys

import fncli

from sesh import analyze, export, health, search, show, stats, sync, timeline


def main() -> None:
    _ = analyze, export, health, search, show, stats, sync, timeline
    fncli.run(["sesh", *sys.argv[1:]])
