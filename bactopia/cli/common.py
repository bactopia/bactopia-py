"""Shared CLI decorators and helpers for Bactopia commands."""

import functools
import logging

import rich.console
import rich_click as click
from rich.logging import RichHandler

import bactopia


def common_options(fn):
    """Add --verbose, --silent, and --version/-V to a click command."""

    @click.version_option(bactopia.__version__, "--version", "-V")
    @click.option("--verbose", is_flag=True, help="Print debug related text")
    @click.option("--silent", is_flag=True, help="Only critical errors will be printed")
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


def setup_logging(verbose: bool, silent: bool) -> None:
    """Configure root logger with RichHandler at the appropriate level."""
    logging.basicConfig(
        format="%(asctime)s:%(name)s:%(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True, console=rich.console.Console(stderr=True))
        ],
    )
    logging.getLogger().setLevel(
        logging.ERROR if silent else logging.DEBUG if verbose else logging.INFO
    )
