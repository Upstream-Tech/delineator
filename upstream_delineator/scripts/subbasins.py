r"""
Delineation of watershed subbasins, using data from
MERIT-Basins and MERIT-Hydro.
Created by Matthew Heberger, May 2024.

See README for more detailed instructions.

Quick Start:

First, set parameters in the file config.py.

Run this script from the command line with two required arguments:
$ python subbasins.py outlets.csv testrun

or with a full file path as follows on Windows or Linux:
$ python subbasins.py C:\Users\matt\Desktop\outlets.csv test
$ python subbasins.py /home/files/outlets.csv test

or in Python as follows:
>> from subbasins import delineate
>> delineate('outlets.csv', 'testrun')

"""

# Standard Python libraries. See requirements.txt for recommended versions.
import argparse
import sys
sys.path.insert(0, ".")
import inspect

# My stuff
from upstream_delineator.delineator_utils.delineate import delineate
from upstream_delineator.config import _GLOBAL_CONFIG


if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "input_csv",
        help="CSV of outlets to delineate.",
    )
    argparser.add_argument(
        "output_prefix",
        help="Prefix for output files from this run.",
    )
    for key, default_val in _GLOBAL_CONFIG.items():
        if default_val is True:
            argparser.add_argument(
                f"--NO_{key}",
                action="store_true",
            ) 
        elif default_val is False:
            argparser.add_argument(
                f"--{key}",
                action="store_true",
            ) 
        else:
            argparser.add_argument(
                f"--{key}",
                type=type(default_val),
                default=default_val,
            )
    args = argparser.parse_args()
    config_vals = {}
    for key, val in vars(args).items():
        if key in _GLOBAL_CONFIG:
            config_vals[key] = val 
        elif (stripped_key := key.removeprefix("NO_")) in _GLOBAL_CONFIG:
            config_vals[stripped_key] = not val 
    
    delineate(args.input_csv, args.output_prefix, config_vals=config_vals)