#!/usr/bin/env python2.7

#(c) 2015-2016 by Authors
#This file is a part of Nano-Align program.
#Released under the BSD license (see LICENSE file)

"""
Runs identification test and report p-values
"""

import sys
import argparse

from nanoalign.pvalues_test import pvalues_test
from nanoalign.model_loader import load_model
from nanoalign.__version__ import __version__


def main():
    parser = argparse.ArgumentParser(description="Nano-Align protein "
                                     "identification", formatter_class= \
                                     argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("blockades_file", metavar="blockades_file",
                        help="path to blockades file (in mat format)")
    parser.add_argument("model_file", metavar="model_file",
                        help="path to trained model file (in Python's pickle format)")
    parser.add_argument("-c", "--cluster-size", dest="cluster_size", type=int,
                        default=10, help="blockades cluster size")
    parser.add_argument("-d", "--database", dest="database",
                        metavar="database", help="database file (in FASTA "
                        "format). If not set, random database is generated",
                        default=None)
    parser.add_argument("-s", "--single-blockades", action="store_true",
                        default=False, dest="single_blockades",
                        help="print statistics for each blockade in a cluster")

    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()

    model = load_model(args.model_file)
    pvalues_test(args.blockades_file, args.cluster_size, model,
                 args.database, args.single_blockades, sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
