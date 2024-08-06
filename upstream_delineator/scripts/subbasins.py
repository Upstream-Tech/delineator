import argparse
import sys

sys.path.insert(0, ".")

from upstream_delineator.config import _GLOBAL_CONFIG

from upstream_delineator.delineator_utils.delineate import delineate

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