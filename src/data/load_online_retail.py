"""
Load the Online Retail II dataset from raw Excel files.

Expected location: ``data/raw/online_retail_II.xlsx``
The file contains two sheets (Year 2009-2010 and Year 2010-2011).
Both sheets are concatenated into a single DataFrame with standardised
column names matching ``src.data.schema.RAW_TO_CLEAN_RENAME``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.schema import RAW_TO_CLEAN_RENAME

_DEFAULT_RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
_DEFAULT_FILE = _DEFAULT_RAW_DIR / "online_retail_II.xlsx"


def load_raw(path: Path | str | None = None) -> pd.DataFrame:
    """Read the raw Excel file and return a single renamed DataFrame.

    Parameters
    ----------
    path:
        Path to the ``.xlsx`` file.  Defaults to
        ``<project>/data/raw/online_retail_II.xlsx``.

    Returns
    -------
    pd.DataFrame
        Concatenated rows from both sheets with columns renamed to the
        canonical snake_case names.

    Raises
    ------
    FileNotFoundError
        If the file does not exist at the resolved path.
    """
    file = Path(path) if path is not None else _DEFAULT_FILE
    if not file.exists():
        raise FileNotFoundError(
            f"Raw data file not found: {file}\n"
            "Download the Online Retail II dataset and place it at the path above, "
            "or use src.data.sample_data.generate_sample() for a synthetic demo."
        )

    sheets = pd.read_excel(file, sheet_name=None)
    frames = list(sheets.values())
    df = pd.concat(frames, ignore_index=True)
    df.rename(columns=RAW_TO_CLEAN_RENAME, inplace=True)
    return df
