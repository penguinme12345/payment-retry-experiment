"""Statistical analysis of the retry timing experiment (PRD-D).

Entry points: ``python -m retrylab.analysis`` (CLI) and :func:`retrylab.analysis.run.run_analysis`.
"""

from retrylab.analysis.run import build_results, run_analysis

__all__ = ["build_results", "run_analysis"]
