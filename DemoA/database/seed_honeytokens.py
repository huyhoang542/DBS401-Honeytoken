"""Backward-compatible command to validate staged SDV/HMA candidates.

Run `generate_hma_honeytokens.py` first. This command performs a dry run by
default; pass `--apply` to commit the staged rows.
"""

from apply_hma_honeytokens import main


if __name__ == "__main__":
    main()
