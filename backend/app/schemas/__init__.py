"""Pydantic v2 request and response schemas for the API layer.

Schemas validate everything crossing the process boundary (contract
guardrail: Pydantic validation for all data exchange). They never compute
money figures; every figure comes from the domain engine or SQL aggregates
assembled by the routers.
"""
