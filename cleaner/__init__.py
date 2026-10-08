"""Metadata cleaning: detect a file's type, read its metadata, strip it."""

from .detect import detect
from .engines import CleanError, UnsupportedFormat
from .metadata import read_metadata
from .pipeline import clean_file

__all__ = ["CleanError", "UnsupportedFormat", "clean_file", "detect", "read_metadata"]
