import sys

import fncli

from sesh import (
    analyze,
    distribution,
    export,
    health,
    index,
    search,
    show,
    stats,
    sync,
    tail,
    timeline,
    tokens,
)


def main() -> None:
    _ = (
        analyze,
        distribution,
        export,
        health,
        index,
        search,
        show,
        stats,
        sync,
        tail,
        timeline,
        tokens,
    )
    fncli.run(["sesh", *sys.argv[1:]])
