import sys

import fncli

from sesh import (
    analyze,
    distribution,
    export,
    health,
    search,
    show,
    stats,
    sync,
    tail,
    timeline,
    tokens,
    verify,
)


def main() -> None:
    _ = (
        analyze,
        distribution,
        export,
        health,
        search,
        show,
        stats,
        sync,
        tail,
        timeline,
        tokens,
        verify,
    )
    fncli.run(["sesh", *sys.argv[1:]])
