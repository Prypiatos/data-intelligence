from .model import AnomalyDetector
from .trainer import train

__all__ = ["AnomalyDetector", "run", "train"]


def run(*args, **kwargs):  # type: ignore[misc]
    from .pipeline import run as _run

    return _run(*args, **kwargs)
