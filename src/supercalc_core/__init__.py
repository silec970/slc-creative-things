"""Public API for the SuperCalc core.

The core package has no GUI dependency. It can be embedded directly, used by
the command line interface, or driven by the desktop worker process.
"""

from .api import Engine
from .diagnostics import Diagnostic, Severity, Span
from .models import EvaluationResult, RunResult, Value

API_VERSION = 1
APP_VERSION = "0.1.0"

__all__ = [
    "API_VERSION",
    "APP_VERSION",
    "Diagnostic",
    "Engine",
    "EvaluationResult",
    "RunResult",
    "Severity",
    "Span",
    "Value",
]
