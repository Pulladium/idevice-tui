from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("idevice-tui")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.1.0"
