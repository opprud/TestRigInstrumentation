#!/usr/bin/env python3
"""
Inspect HDF5 file structure and metadata.
"""
import sys
import h5py
import numpy as np

def inspect_hdf5(filepath):
    """Print HDF5 file structure, groups, datasets, and attributes."""
    print(f"\nInspecting: {filepath}\n")
    print("=" * 70)

    with h5py.File(filepath, "r") as f:
        def print_attrs(name, obj):
            """Print attributes of an HDF5 object."""
            indent = "  " * name.count("/")
            if isinstance(obj, h5py.Group):
                print(f"{indent}📁 {name.split('/')[-1] or '/'}")
            elif isinstance(obj, h5py.Dataset):
                shape = obj.shape
                dtype = obj.dtype
                print(f"{indent}📊 {name.split('/')[-1]} {shape} {dtype}")

            # Print attributes
            for key, val in obj.attrs.items():
                print(f"{indent}  ├─ {key}: {val}")

        # Walk through all objects
        f.visititems(print_attrs)

        # Print root attributes
        print("\n📌 Root attributes:")
        for key, val in f.attrs.items():
            print(f"  ├─ {key}: {val}")

    print("=" * 70)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 inspect_hdf5.py <file.hdf5>")
        sys.exit(1)

    inspect_hdf5(sys.argv[1])
