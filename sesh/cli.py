import sys

import fncli

from sesh import (
    analyze,
    distribution,
    export,
    gc,
    health,
    histogram,
    list,
    search,
    show,
    stats,
    status,
    sync,
    timeline,
    tokens,
    trend,
    verify,
)


def main() -> None:
    _ = (
        analyze,
        distribution,
        export,
        gc,
        health,
        histogram,
        list,
        search,
        show,
        stats,
        status,
        sync,
        timeline,
        tokens,
        trend,
        verify,
    )
    fncli.run(["sesh", *(sys.argv[1:] or ["--help"])])
