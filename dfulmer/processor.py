#!/usr/bin/env python3
"""
This script extracts info from bibliographic records
"""

import sys
import argparse
from extract_bibs.extract import Extract
from pymarc import MARCReader
from collections import defaultdict

def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', dest='infile', help='input file', required=True)
    parser.add_argument('-o', dest='outbase', help='output base', required=True)
    args = parser.parse_args(args=argv)

    infile = args.infile
    outbase = args.outbase
    outfile = outbase + '.txt'
    rptfile = outbase + '_rpt.txt'

    try:
        out = open(outfile, "w", encoding="utf-8")
        rpt = open(rptfile, "w")
    except:
        print("Can't open file(s) for output.")
        exit(1)

    (
        reccnt,
        no_008,
        no_subj_cnt,
        subj_cnt,
        level_cnt,
        no_996,
        date_skip_cnt,
        no_stdnum,
        isbn_cnt,
        outcnt,
        f996_matched,
        f996_search_cnt_skip,
        f996_searched_cnt,
        own_not_miu,
        arrival_date,
        no_arrival_date,
        arrival_date_out_of_range,
    ) = (0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)
    date_source = defaultdict(int)

    with open(infile, 'rb') as fh:
        reader = MARCReader(fh, force_utf8=True)
        for record in reader:
            extract = Extract(record)
            result = extract.process()
            reccnt += 1
            if reccnt % 1000 == 0:
                print(f"{reccnt} ({record['001'].value()}): processing record")
            if result['no 008 field'] == '1':
                print(f"{reccnt}: no 008 field for record")
                no_008 += 1
                continue
            if result['no arrival date'] == '1':
                no_arrival_date += 1
                date_source[result['source of date']] += 1
                continue
            out.write(result['line'] + "\n")
            date_source[result['source of date']] += 1
            outcnt += 1

    rpt.write(f"infile is {infile}\n")
    rpt.write(f"outfile is {outfile}\n")
    rpt.write(f"{sys.argv[0]}--{' '.join(sys.argv[1:])}\n")
    rpt.write(f"{reccnt} records read\n")
    rpt.write(f"{no_008} no 008 field for record, skipped\n")
    rpt.write(f"{no_arrival_date} no arrival date for record, skipped\n")
    rpt.write(f"{no_stdnum} no stdnum in record\n")
    rpt.write(f"{outcnt} records written\n")
    rpt.write("\n")

    for key in sorted(date_source):
        rpt.write(f"{key}: {date_source[key]}\n")


    return 0 # ok status

if __name__=='__main__':
    sys.exit(main())