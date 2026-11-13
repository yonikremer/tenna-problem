"""Dump all NetCDF attributes (global and per-variable) of the recordings to JSON.

The assignment says the file is self-describing. This is the script that reads that description, so
every metadata claim in the report can be traced back to an attribute instead of a guess.

Usage: python -m analysis.dump_attrs gnss_observation.nc [more.nc ...]
"""

import json
import sys

import netCDF4


def jsonable(value):
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def dump(path):
    with netCDF4.Dataset(path) as dataset:
        return {
            "file": path,
            "file_format": dataset.file_format,
            "data_model": dataset.data_model,
            "dimensions": {name: len(value) for name, value in dataset.dimensions.items()},
            "global_attributes": {name: jsonable(getattr(dataset, name)) for name in dataset.ncattrs()},
            "variables": {
                name: {
                    "dtype": str(variable.dtype),
                    "dimensions": list(variable.dimensions),
                    "shape": list(variable.shape),
                    "attributes": {
                        attribute: jsonable(getattr(variable, attribute))
                        for attribute in variable.ncattrs()
                    },
                }
                for name, variable in dataset.variables.items()
            },
        }


def main(paths):
    for source in paths:
        destination = source.rsplit(".", 1)[0] + "_attrs.json"
        try:
            data = dump(source)
        except OSError as error:
            raise SystemExit(f"cannot read {source}: {error}") from error
        try:
            with open(destination, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError as error:
            raise SystemExit(f"cannot write {destination}: {error}") from error
        print(
            f"{source} -> {destination} "
            f"({len(data['global_attributes'])} global attrs, {len(data['variables'])} vars)"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
