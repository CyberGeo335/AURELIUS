"""Portable AURELIUS scoring, decision and offer package."""

__all__ = ["evaluate_application"]


def evaluate_application(snapshot, policy, predictor=None):
    from .pipeline import evaluate_application as evaluate
    return evaluate(snapshot, policy, predictor)
