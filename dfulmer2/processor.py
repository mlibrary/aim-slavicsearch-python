#!/usr/bin/env python3
"""CLI entry for the dfulmer2 report-stage port.

Run from the repo root:
    python3 dfulmer2/processor.py -i <input> -o <outbase>

This is a thin wrapper: it parses args, loads .env, builds the three
collaborating objects (WorldCatClient, ReportSet, Counters), wires them
into a Pipeline, and runs it. All the logic lives in the report_bibs
package next door.
"""
import argparse
import os
import sys
from pathlib import Path

from report_bibs.line_io import Counters
from report_bibs.pipeline import Pipeline
from report_bibs.reports import ReportSet
from report_bibs.worldcat import WorldCatClient


def load_env(path):
    """Tiny .env reader: KEY=value lines, # comments, optional quotes."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, val = line.partition("=")
        k, val = k.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        os.environ.setdefault(k, val)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='dfulmer2/processor.py',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-i', dest='infile', required=True, help='input key file')
    parser.add_argument('-o', dest='outbase', required=True, help='output filename base')
    args = parser.parse_args(argv)

    # Look for .env in the repo root (parent of dfulmer2/).
    repo_root = Path(__file__).resolve().parent.parent
    load_env(repo_root / '.env')

    try:
        client = WorldCatClient.from_env()
    except KeyError as e:
        sys.exit(f"missing env var {e}; set WSKEY_CLIENT_ID and WSKEY_SECRET in .env")

    with ReportSet(args.outbase) as reports:
        counters = Counters()
        pipeline = Pipeline(client, reports, counters)
        pipeline.install_signal_handlers()
        try:
            pipeline.run(args.infile)
        finally:
            client.close()


if __name__ == '__main__':
    sys.exit(main())
