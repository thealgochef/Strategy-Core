"""The strategy.json contract: one Pydantic schema + a strict fail-closed loader.

Previously duplicated (research had the emitter dict, Trade-Lab had the loader).
Now a single definition both repos import, so the contract *format* cannot drift.
"""
