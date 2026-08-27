"""Held-out benchmark bank.

These items are deliberately NOT produced by any generator: they are a fixed,
private evaluation set used by the benchmark-rotation policy. Their answers
live in these JSON files server-side and are never returned by a public API.

If this bank were ever published, its value would be destroyed — which is
exactly the property that motivates dynamic generation for the other 85% of
tasks. The bank exists so that a validator can occasionally measure miners on a
stable yardstick and detect drift in the generated pool.
"""

from .loader import (BenchmarkBank, benchmark_generators, load_bank,
                     register_benchmark_generators)

__all__ = ["BenchmarkBank", "load_bank", "benchmark_generators",
           "register_benchmark_generators"]
