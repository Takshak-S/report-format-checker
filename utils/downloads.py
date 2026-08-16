"""
utils/downloads.py

Utilities for downloading dataframes and creating ZIP archives.
"""
import io
import pandas as pd
import zipfile

def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Converts a DataFrame to CSV bytes."""
    return df.to_csv(index=False).encode("utf-8")

def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Converts a DataFrame to Excel bytes."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def dataframe_to_json_bytes(df: pd.DataFrame) -> bytes:
    """Converts a DataFrame to JSON bytes."""
    return df.to_json(orient="records").encode("utf-8")

def create_zip_archive(files: list[tuple[str, bytes]]) -> bytes:
    """
    Creates a ZIP archive from a list of (filename, file_bytes).
    Returns the ZIP file as bytes.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in files:
            zf.writestr(filename, data)
    return zip_buffer.getvalue()
