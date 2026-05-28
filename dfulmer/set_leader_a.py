#!/usr/bin/env python3
"""Set MARC leader[9] = 'a' on every record. Outputs <stem>_with_as.mrc."""
import argparse
import sys
from pathlib import Path
from pymarc import MARCReader, MARCWriter


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("infile", help="input MARC binary file")
    args = p.parse_args()

    in_path = Path(args.infile)
    if in_path.suffix == ".mrc":
        out_path = in_path.with_name(in_path.stem + "_with_as.mrc")
    else:
        out_path = in_path.with_name(in_path.name + "_with_as.mrc")

    if out_path.resolve() == in_path.resolve():
        sys.exit(f"refusing to overwrite input: {in_path}")

    read = written = already_a = flipped = 0
    with open(in_path, "rb") as fh_in, open(out_path, "wb") as fh_out:
        reader = MARCReader(fh_in, to_unicode=False)
        writer = MARCWriter(fh_out)
        for record in reader:
            read += 1
            if record is None:
                continue
            if record.leader[9] == "a":
                already_a += 1
            else:
                flipped += 1
            record.leader[9] = "a"
            writer.write(record)
            written += 1
        writer.close()

    print(f"read {read} records, wrote {written} to {out_path}")
    print(f"  {already_a} already had leader[9]='a', {flipped} flipped")


if __name__ == "__main__":
    sys.exit(main())