"""Data-analysis tasks over small synthetic tabular datasets.

The dataset is generated from a seed, injected anomalies are known by
construction, and every statistic is computed with the standard library so the
ground truth is exact.
"""

from __future__ import annotations

import random
import statistics
from typing import Dict, List, Optional, Tuple

from ..protocol.messages import Category, VerificationType
from .base import BaseGenerator, GeneratedTask, GroundTruth, register

_REGIONS = ["eu-west", "us-east", "ap-south", "sa-east"]
_STATUS = ["ok", "ok", "ok", "degraded"]


def _make_table(rng: random.Random, rows: int, anomalies: int
                ) -> Tuple[List[Dict[str, object]], List[str]]:
    base = rng.randint(80, 140)
    spread = rng.randint(4, 12)
    table: List[Dict[str, object]] = []
    for i in range(rows):
        table.append({
            "id": f"n{i+1:02d}",
            "region": rng.choice(_REGIONS),
            "latency_ms": max(1, int(rng.gauss(base, spread))),
            "status": rng.choice(_STATUS),
        })
    anomaly_ids: List[str] = []
    for row in rng.sample(table, anomalies):
        row["latency_ms"] = int(base + spread * rng.uniform(6, 10))
        anomaly_ids.append(str(row["id"]))
    return table, sorted(anomaly_ids)


def _render(table: List[Dict[str, object]]) -> str:
    head = "id,region,latency_ms,status"
    body = "\n".join(
        f"{r['id']},{r['region']},{r['latency_ms']},{r['status']}" for r in table
    )
    return head + "\n" + body


@register
class AnomalyDetectionGenerator(BaseGenerator):
    """Identify injected outliers (ground truth known by construction)."""

    name = "data.anomaly"
    category = Category.DATA
    verification_type = VerificationType.PROGRAMMATIC
    default_timeout_s = 30

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        rows = 12 + difficulty * 2
        k = 1 if difficulty <= 3 else (2 if difficulty <= 7 else 3)
        table, anomalies = _make_table(rng, rows, k)
        prompt = (
            "The CSV below records validator probe latencies.\n\n```csv\n"
            + _render(table)
            + "\n```\n\nIdentify the anomalous node id(s) whose latency is a clear outlier "
              "(> 4 standard deviations above the non-outlier mean). "
              "Answer with a comma-separated list of ids only."
        )
        gt = GroundTruth(
            answer=", ".join(anomalies), verifier="set_match",
            params={"items": anomalies, "min_f1": 0.0},
            evidence_keywords=["standard deviation", "outlier", "z-score", "mean"],
            explanation=f"{k} outlier(s) injected at generation time: {anomalies}",
        )
        req = self.build_request(prompt, difficulty,
                                 answer_schema={"type": "list", "of": "id"})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "table", "table": table,
                                            "anomalies": anomalies})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        spec = task.mutation_spec
        if spec.get("kind") != "table":
            return None
        table = [dict(r) for r in spec["table"]]
        rng.shuffle(table)  # row order is irrelevant
        prompt = (
            "Rows below are in a different order but describe the same probe run.\n\n```csv\n"
            + _render(table)
            + "\n```\n\nList the anomalous node id(s), comma separated."
        )
        req = self.build_request(prompt, task.request.difficulty,
                                 verification_type=VerificationType.ADVERSARIAL,
                                 parent_task_id=task.request.task_id)
        gt = GroundTruth(answer=task.ground_truth.answer, verifier="set_match",
                         params=dict(task.ground_truth.params),
                         explanation="Row order shuffled; anomalies invariant.")
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={**spec, "table": table})


@register
class StatisticGenerator(BaseGenerator):
    """Compute an exact statistic over a generated table."""

    name = "data.statistic"
    category = Category.DATA
    verification_type = VerificationType.PROGRAMMATIC

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        rows = 10 + difficulty
        table, _ = _make_table(rng, rows, 0)
        stat = rng.choice(["median", "mean_region", "p90", "count_degraded"])
        values = [int(r["latency_ms"]) for r in table]
        if stat == "median":
            answer = f"{statistics.median(values):.2f}"
            question = "the median of `latency_ms` across all rows (2 dp)"
        elif stat == "mean_region":
            region = rng.choice(sorted({str(r["region"]) for r in table}))
            subset = [int(r["latency_ms"]) for r in table if r["region"] == region]
            answer = f"{statistics.fmean(subset):.2f}"
            question = f"the mean `latency_ms` for region `{region}` (2 dp)"
        elif stat == "p90":
            ordered = sorted(values)
            idx = max(0, min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1)))))
            answer = f"{ordered[idx]:.2f}"
            question = ("the 90th percentile of `latency_ms` using nearest-rank on the "
                        "zero-indexed sorted array (2 dp)")
        else:
            answer = str(sum(1 for r in table if r["status"] == "degraded"))
            question = "the number of rows whose `status` is `degraded`"
        prompt = ("```csv\n" + _render(table) + "\n```\n\nCompute " + question
                  + ". Answer with the number only.")
        gt = GroundTruth(answer=answer, verifier="numeric",
                         params={"atol": 0.01, "rtol": 0.0},
                         evidence_keywords=["sort", "sum", "count", "aggregate"],
                         explanation=f"Computed with the stdlib: {answer}")
        req = self.build_request(prompt, difficulty, answer_schema={"type": "number"})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate", "prompt": prompt,
                                            "answer": answer})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        from .math_tasks import _restate_mutation

        return _restate_mutation(self, task, rng)


@register
class RelationshipGenerator(BaseGenerator):
    """Classify the relationship between two generated numeric series."""

    name = "data.relationship"
    category = Category.DATA
    verification_type = VerificationType.EXACT

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        n = 10 + difficulty
        kind = rng.choice(["positive", "negative", "none"])
        xs = [round(rng.uniform(1, 100), 1) for _ in range(n)]
        noise = 4 if difficulty <= 5 else 12
        if kind == "positive":
            ys = [round(2.1 * x + rng.uniform(-noise, noise), 1) for x in xs]
        elif kind == "negative":
            ys = [round(180 - 1.7 * x + rng.uniform(-noise, noise), 1) for x in xs]
        else:
            ys = [round(rng.uniform(20, 160), 1) for _ in xs]
        # verify the label actually holds for the realised sample
        r = _pearson(xs, ys)
        label = "positive" if r > 0.5 else ("negative" if r < -0.5 else "none")
        table = "\n".join(f"{x},{y}" for x, y in zip(xs, ys))
        prompt = (
            "```csv\nthroughput,latency\n" + table + "\n```\n\n"
            "Classify the linear relationship between `throughput` and `latency` as "
            "POSITIVE, NEGATIVE or NONE (|Pearson r| <= 0.5 counts as NONE)."
        )
        gt = GroundTruth(answer=label, verifier="exact",
                         params={"aliases": [label.upper()]},
                         evidence_keywords=["pearson", "correlation", "covariance", "slope"],
                         explanation=f"Pearson r = {r:.3f} -> {label}")
        req = self.build_request(prompt, difficulty,
                                 answer_schema={"type": "enum",
                                                "values": ["POSITIVE", "NEGATIVE", "NONE"]})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "restate", "prompt": prompt,
                                            "answer": label})

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        from .math_tasks import _restate_mutation

        return _restate_mutation(self, task, rng)


def _pearson(xs: List[float], ys: List[float]) -> float:
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return 0.0 if dx == 0 or dy == 0 else num / (dx * dy)
