"""Read-only, source-grounded retrieval of application requirements."""

from .pipeline import RequirementsRAG, is_requirements_question

__all__ = ['RequirementsRAG', 'is_requirements_question']
