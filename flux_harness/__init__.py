"""One shared lifecycle harness. Agent packages supply only bounded job logic."""
from .runtime import Context,Result,Harness,run_job
from .bindings import BoundRunner
