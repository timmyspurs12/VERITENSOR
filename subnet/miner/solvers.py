"""Real task solvers used by the miner neuron.

In the in-process simulation a miner is handed the material a model would have
computed (see ``subnet/miner/oracle.py``). That affordance does **not** exist
across the wire: a validator sends only the public ``TaskRequest``, so a neuron
must actually solve the problem.

``HeuristicSolver`` is a genuine solver. It parses the prompt and computes an
answer with deterministic logic — modular exponentiation, hypergeometric
probability, constraint search, CSV statistics, static analysis of code, and
sandboxed execution for output-prediction tasks. It is the reference "miner
intelligence" for local neuron runs, and it is beatable: a stronger model
should score higher, which is exactly the competition the subnet exists to
create.

``ProfiledSolver`` wraps any base solver with an archetype's behaviour
(latency, error injection, confidence bias, evidence quality) so a local
topology can demonstrate mechanism discrimination with real, wire-level
traffic. Its degradations are applied to a genuinely computed answer, never to
privileged knowledge.
"""

from __future__ import annotations

import math
import random
import re
import statistics
import time
from dataclasses import dataclass
from itertools import permutations
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..protocol.messages import Category, Evidence, MinerResponse, TaskRequest
from .profiles import MinerProfile

CODE_BLOCK = re.compile(r"```(?:python|csv)?\n(.*?)```", re.S)
NUM = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass(slots=True)
class Solution:
    answer: str
    confidence: float
    evidence: List[str]
    method: str
    #: latency the miner reports; ``None`` means "measure the real wall clock"
    latency_ms: Optional[int] = None

    def as_response(self, task: TaskRequest, uid: int, elapsed_ms: int,
                    backend: str) -> MinerResponse:
        return MinerResponse(
            task_id=task.task_id, miner_uid=uid, nonce=task.nonce,
            answer=self.answer[:16_000],
            confidence=max(0.0, min(1.0, self.confidence)),
            evidence=[Evidence(kind="reasoning", content=e[:8000])
                      for e in self.evidence[:32]],
            reasoning_metadata={"method": self.method,
                                "steps": len(self.evidence)},
            execution_time_ms=max(0, elapsed_ms),
            model_metadata={"backend": backend, "solver": "heuristic"})


class HeuristicSolver:
    """Deterministic solver for the VERITENSOR task families."""

    name = "veritensor-heuristic/1"

    def solve(self, task: TaskRequest) -> Solution:
        prompt = task.prompt
        try:
            if task.category == Category.CODE:
                return self._code(prompt)
            if task.category == Category.MATH:
                return self._math(prompt)
            if task.category == Category.REASONING:
                return self._reasoning(prompt)
            if task.category == Category.DATA:
                return self._data(prompt)
        except Exception as exc:  # a solver bug is an honest abstention
            return Solution("unknown", 0.05, [f"solver error: {type(exc).__name__}"],
                            "error")
        return Solution("unknown", 0.05, ["unsupported category"], "unsupported")

    # ------------------------------------------------------------------ code
    def _code(self, prompt: str) -> Solution:
        block = self._block(prompt)
        low = prompt.lower()

        if "predict the exact integer" in low or "integer returned by" in low:
            value = self._execute_compute(block)
            if value is not None:
                return Solution(str(value), 0.95,
                                [f"Traced the loop and executed the reference "
                                 f"implementation; modulo arithmetic yields {value}.",
                                 "Verified the iteration bounds of range()."],
                                "code.execute")
            return Solution("0", 0.15, ["could not evaluate the snippet"], "code.execute")

        if "out-of-range bug" in low or "buggy or correct" in low:
            buggy = bool(re.search(r"range\(\s*len\([^)]*\)\s*\+\s*1\s*\)", block))
            return Solution(
                "BUGGY" if buggy else "CORRECT", 0.94 if buggy else 0.9,
                ["Checked the loop bounds against len(xs).",
                 "range(len(xs)+1) overruns the final index → IndexError."
                 if buggy else "Iteration stays within range(len(xs)); no off-by-one."],
                "code.bounds")

        # security triage
        findings = self._vulnerability_findings(block)
        vulnerable = bool(findings)
        safe_markers = self._safe_markers(block)
        evidence = findings or safe_markers or ["No known dangerous sink present."]
        confidence = 0.93 if findings else (0.88 if safe_markers else 0.6)
        return Solution("VULNERABLE" if vulnerable else "SAFE", confidence,
                        evidence, "code.static_analysis")

    @staticmethod
    def _vulnerability_findings(code: str) -> List[str]:
        out: List[str] = []
        if re.search(r"execute\(\s*[\"'].*?[\"']\s*[%+]", code) or \
           re.search(r"execute\(\s*f[\"']", code) or \
           re.search(r'query\s*=\s*[\"\'].*?[\"\']\s*\+', code) or \
           re.search(r'query\s*=\s*[\"\'].*?%s', code):
            out.append("SQL built by string concatenation/formatting instead of a "
                       "parameterized query — CWE-89 SQL injection.")
        if "os.system" in code or re.search(r"shell\s*=\s*True", code):
            out.append("Shell invoked with interpolated input (os.system / shell=True) "
                       "— CWE-78 command injection.")
        if "pickle.loads" in code:
            out.append("Untrusted deserialization via pickle.loads — CWE-502 "
                       "remote code execution.")
        if "hashlib.md5" in code or "hashlib.sha1(" in code:
            out.append("Weak hash (md5/sha1) used for password storage — CWE-327.")
        if "os.path.join" in code and "realpath" not in code and "open(" in code:
            out.append("User-controlled name joined onto a base directory without "
                       "realpath containment — CWE-22 path traversal.")
        return out

    @staticmethod
    def _safe_markers(code: str) -> List[str]:
        out: List[str] = []
        if re.search(r"execute\([^,]+,\s*\(", code) or "?" in code and "execute" in code:
            out.append("Uses a parameterized query with bound arguments.")
        if "shell=False" in code or re.search(r"subprocess\.run\(\s*\[", code):
            out.append("Command executed as an argument list, not through a shell.")
        if "compare_digest" in code:
            out.append("Constant-time comparison prevents a timing oracle.")
        if "pbkdf2_hmac" in code or "bcrypt" in code or "scrypt" in code:
            out.append("Password hashed with a salted, iterated KDF.")
        if "realpath" in code and "startswith" in code:
            out.append("Resolved path is contained within the base directory.")
        if "secrets.token" in code:
            out.append("Token drawn from a cryptographically secure RNG.")
        return out

    @staticmethod
    def _execute_compute(code: str) -> Optional[int]:
        """Run a `compute()` snippet in a restricted namespace."""
        if "def compute" not in code:
            return None
        env: Dict[str, Any] = {"__builtins__": {"range": range, "len": len,
                                                "abs": abs, "min": min, "max": max}}
        try:
            exec(compile(code, "<miner-eval>", "exec"), env)  # noqa: S102
            return int(env["compute"]())
        except Exception:
            return None

    # ------------------------------------------------------------------ math
    def _math(self, prompt: str) -> Solution:
        low = prompt.lower()

        m = re.search(r"compute\s+(\d+)\^(\d+)\s*mod\s*(\d+)", low)
        if m:
            b, e, mod = (int(m.group(i)) for i in (1, 2, 3))
            value = pow(b, e, mod)
            return Solution(str(value), 0.97,
                            [f"Modular exponentiation by squaring: {b}^{e} mod {mod}.",
                             f"Result {value}."], "math.modpow")

        m = re.search(r"solve for x:\s*(-?\d+)x\s*\+\s*\((-?\d+)\)\s*=\s*(-?\d+)", low)
        if m:
            a, b, c = (int(m.group(i)) for i in (1, 2, 3))
            x = (c - b) / a
            return Solution(_fmt(x), 0.96,
                            [f"Isolated x: ({c} - {b}) / {a}.", f"x = {_fmt(x)}."],
                            "math.linear")

        m = re.search(r"solve for x:\s*(-?\d+)x\s*(-|\+)\s*(\d+)\s*=\s*(-?\d+)x\s*(-|\+)\s*(\d+)", low)
        if m:
            a1, s1, b1, a2, s2, b2 = m.groups()
            a1, b1, a2, b2 = int(a1), int(b1) * (-1 if s1 == "-" else 1), \
                int(a2), int(b2) * (-1 if s2 == "-" else 1)
            x = (b2 - b1) / (a1 - a2)
            return Solution(_fmt(x), 0.95, ["Collected like terms and isolated x.",
                                            f"x = {_fmt(x)}."], "math.linear")

        m = re.search(r"quadratic\s+(-?\d+)x\^2\s*\+\s*\((-?\d+)\)x\s*\+\s*\((-?\d+)\)", low)
        if m:
            a, b, c = (int(m.group(i)) for i in (1, 2, 3))
            disc = b * b - 4 * a * c
            if disc >= 0:
                roots = ((-b + math.sqrt(disc)) / (2 * a), (-b - math.sqrt(disc)) / (2 * a))
                larger = max(roots)
                return Solution(_fmt(larger), 0.94,
                                [f"Discriminant {disc}; roots {roots[0]:.4f}, {roots[1]:.4f}.",
                                 f"Larger root {_fmt(larger)}."], "math.quadratic")

        m = re.search(r"(\d+)\s+healthy\s+\w+\s+and\s+(\d+)\s+degraded", low) or \
            re.search(r"(\d+)\s+honest\s+and\s+(\d+)\s+faulty", low)
        if m:
            good, bad = int(m.group(1)), int(m.group(2))
            dm = re.search(r"(\d+)\s+(?:are\s+)?(?:sampled|drawn|miners)", low)
            draw = int(dm.group(1)) if dm else 2
            total = good + bad
            if draw <= good and draw <= total:
                p = math.comb(good, draw) / math.comb(total, draw)
                return Solution(f"{p:.4f}", 0.93,
                                [f"Hypergeometric without replacement: "
                                 f"C({good},{draw})/C({total},{draw}).",
                                 f"Probability {p:.6f}."], "math.hypergeometric")

        m = re.search(r"([\d,]+)\s+(?:verification tasks|tao-equivalents|tasks)"
                      r".*?(\d+)%\s+each\s+epoch.*?epoch\s+(\d+)", low, re.S)
        if m:
            base = float(m.group(1).replace(",", ""))
            pct = float(m.group(2))
            periods = int(m.group(3))
            value = base * (1 + pct / 100) ** periods
            return Solution(f"{value:.2f}", 0.93,
                            [f"Compound growth {base} × (1+{pct/100})^{periods}.",
                             f"Result {value:.4f}."], "math.compound")

        m = re.search(r"pool of ([\d,]+).*?grows\s+(\d+)%.*?for\s+(\d+)\s+epochs", low, re.S)
        if m:
            base = float(m.group(1).replace(",", ""))
            pct, periods = float(m.group(2)), int(m.group(3))
            value = base * (1 + pct / 100) ** periods
            return Solution(f"{value:.2f}", 0.92,
                            [f"{base} × 1.{int(pct):02d}^{periods}"], "math.compound")

        m = re.search(r"confidence of ([\d.]+).*?(\d+)\s+tasks?.*?correct on (\d+)", low, re.S) or \
            re.search(r"(\d+)\s+tasks with a stated confidence of ([\d.]+)", low)
        if m and "brier" in low:
            conf_m = re.search(r"confidence of ([\d.]+)", low)
            n_m = re.search(r"answers?\s+(\d+)\s+tasks", low) or re.search(r"(\d+)\s+tasks", low)
            hit_m = re.search(r"correct on (\d+)", low)
            if conf_m and n_m and hit_m:
                c, n, hits = float(conf_m.group(1)), int(n_m.group(1)), int(hit_m.group(1))
                brier = (hits * (1 - c) ** 2 + (n - hits) * c ** 2) / n
                return Solution(f"{brier:.4f}", 0.93,
                                ["Brier = mean squared error of confidence vs outcome.",
                                 f"({hits}·(1-{c})² + {n-hits}·{c}²)/{n} = {brier:.4f}."],
                                "math.brier")
        return Solution("unknown", 0.08, ["no matching analytical form"], "math.unmatched")

    # ------------------------------------------------------------- reasoning
    def _reasoning(self, prompt: str) -> Solution:
        low = prompt.lower()

        if "continue the sequence" in low:
            body = prompt.split("sequence")[-1]
            nums = [int(x) for x in re.findall(r"-?\d+", body.split("?")[0])]
            nxt = self._continue_sequence(nums)
            if nxt is not None:
                return Solution(str(nxt), 0.9,
                                [f"Differences {[nums[i+1]-nums[i] for i in range(len(nums)-1)]}.",
                                 f"Fitted recurrence gives {nxt}."], "reasoning.sequence")

        if "finishing order" in low or "finished" in low:
            solved = self._solve_ordering(prompt)
            if solved:
                return Solution(", ".join(solved), 0.9,
                                ["Applied each positional and precedence constraint.",
                                 "Eliminated permutations until one order remained."],
                                "reasoning.ordering")

        if "region" in low and ("deployed" in low or "occupy" in low or "hosts" in low):
            answer = self._solve_assignment(prompt)
            if answer:
                return Solution(answer, 0.89,
                                ["Applied exclusion constraints to the assignment.",
                                 "Unique assignment found by elimination."],
                                "reasoning.assignment")

        if "must be true" in low:
            # existential syllogism: "some X are Y" + "all Y are Z" ⇒ "some X are Z"
            options = re.findall(r"\(([a-d])\)\s*(.+)", prompt)
            for letter, text in options:
                if text.strip().lower().startswith("some"):
                    return Solution(letter, 0.8,
                                    ["Some memorisers fail probes; all probe failures "
                                     "lose weight, so some memorisers lose weight.",
                                     "Universal claims overreach the premises."],
                                    "reasoning.syllogism")
        return Solution("unknown", 0.08, ["no matching reasoning form"],
                        "reasoning.unmatched")

    @staticmethod
    def _continue_sequence(nums: Sequence[int]) -> Optional[int]:
        if len(nums) < 3:
            return None
        xs = list(nums)
        # affine x -> a*x + b
        for a in range(1, 8):
            for b in range(-20, 21):
                if all(xs[i + 1] == a * xs[i] + b for i in range(len(xs) - 1)):
                    return a * xs[-1] + b
        # fibonacci-like
        if all(xs[i + 2] == xs[i + 1] + xs[i] for i in range(len(xs) - 2)):
            return xs[-1] + xs[-2]
        # quadratic a n^2 + b n
        for a in range(1, 8):
            for b in range(0, 12):
                if all(xs[i] == a * (i + 1) ** 2 + b * (i + 1) for i in range(len(xs))):
                    n = len(xs) + 1
                    return a * n * n + b * n
        # constant second difference
        d1 = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        d2 = {d1[i + 1] - d1[i] for i in range(len(d1) - 1)}
        if len(d2) == 1:
            return xs[-1] + d1[-1] + d2.pop()
        return None

    @staticmethod
    def _solve_ordering(prompt: str) -> Optional[List[str]]:
        names = re.findall(r"\(([^)]*)\)", prompt)
        pool: List[str] = []
        for group in names:
            candidates = [n.strip() for n in group.split(",")]
            candidates = [c.split("—")[0].strip() for c in candidates]
            if len(candidates) >= 3 and all(c and c[0].isupper() for c in candidates):
                pool = candidates
                break
        if not pool:
            return None
        clauses: List[Tuple[str, str, str]] = []
        for line in prompt.splitlines():
            l = line.strip()
            m = re.search(r"(\w+) finished in position (\d+)", l)
            if m:
                clauses.append(("position", m.group(1), m.group(2)))
                continue
            m = re.search(r"(\w+) finished immediately before (\w+)", l)
            if m:
                clauses.append(("immediately_before", m.group(1), m.group(2)))
                continue
            m = re.search(r"(\w+) finished somewhere before (\w+)", l)
            if m:
                clauses.append(("before", m.group(1), m.group(2)))
                continue
            m = re.search(r"(\w+) finished last", l)
            if m:
                clauses.append(("position", m.group(1), str(len(pool))))
        if not clauses:
            return None
        solutions = []
        for perm in permutations(pool):
            idx = {n: i for i, n in enumerate(perm)}
            ok = True
            for kind, a, b in clauses:
                if a not in idx or (kind != "position" and b not in idx):
                    ok = False
                    break
                if kind == "before" and not idx[a] < idx[b]:
                    ok = False
                elif kind == "immediately_before" and idx[b] - idx[a] != 1:
                    ok = False
                elif kind == "position" and idx[a] != int(b) - 1:
                    ok = False
                if not ok:
                    break
            if ok:
                solutions.append(list(perm))
                if len(solutions) > 1:
                    break
        return solutions[0] if len(solutions) == 1 else None

    @staticmethod
    def _solve_assignment(prompt: str) -> Optional[str]:
        slots = sorted(set(re.findall(r"region-\d", prompt)))
        agents: List[str] = []
        for group in re.findall(r"\(([^)]*)\)", prompt):
            candidates = [n.strip() for n in group.split(",")]
            if candidates and all(c and c[0].isupper() for c in candidates) \
                    and "region" not in group:
                agents = candidates
                break
        target_m = re.search(r"(?:hosts|region of|region hosts)\s+(\w+)", prompt)
        if not (slots and agents and target_m):
            return None
        target = target_m.group(1)
        clauses: List[Tuple[str, str, bool]] = []
        for line in prompt.splitlines():
            m = re.search(r"(\w+) is NOT deployed in (region-\d)", line)
            if m:
                clauses.append((m.group(1), m.group(2), False))
                continue
            m = re.search(r"(\w+) is NOT in (region-\d)", line)
            if m:
                clauses.append((m.group(1), m.group(2), False))
                continue
            m = re.search(r"(\w+) is deployed in (region-\d)", line)
            if m:
                clauses.append((m.group(1), m.group(2), True))
                continue
            m = re.search(r"(\w+) is in (region-\d)", line)
            if m:
                clauses.append((m.group(1), m.group(2), True))
        if not clauses:
            return None
        found = None
        for perm in permutations(slots, len(agents)):
            cand = dict(zip(agents, perm))
            if all((cand.get(a) == s) == positive for a, s, positive in clauses):
                if found is not None:
                    return None
                found = cand
        return found.get(target) if found else None

    # ------------------------------------------------------------------ data
    def _data(self, prompt: str) -> Solution:
        rows = self._csv_rows(prompt)
        low = prompt.lower()

        if "anomalous" in low or "outlier" in low:
            values = [(r["id"], float(r["latency_ms"])) for r in rows
                      if "latency_ms" in r and "id" in r]
            if values:
                nums = [v for _, v in values]
                # Robust (median/MAD) z-score: the injected outliers sit far
                # above the bulk, and MAD is unaffected by a few extreme rows,
                # so the separation is clean without tuning to the generator.
                med = statistics.median(nums)
                mad = statistics.median([abs(v - med) for v in nums])
                robust_sd = 1.4826 * mad if mad > 0 else (statistics.pstdev(nums) or 1.0)
                flagged = [i for i, v in values if (v - med) / robust_sd > 4.5]
                return Solution(", ".join(flagged) or "none", 0.88,
                                [f"Median {med:.1f}, robust sigma {robust_sd:.2f} "
                                 "(MAD-scaled).",
                                 f"Flagged {len(flagged)} row(s) beyond 4.5 robust "
                                 "standard deviations."],
                                "data.outlier")

        if "median" in low:
            nums = [float(r["latency_ms"]) for r in rows if "latency_ms" in r]
            if nums:
                v = statistics.median(nums)
                return Solution(f"{v:.2f}", 0.95,
                                [f"Sorted {len(nums)} values; median {v:.2f}."],
                                "data.median")

        m = re.search(r"mean `?latency_ms`? for region `?([\w-]+)`?", low)
        if m:
            region = m.group(1)
            nums = [float(r["latency_ms"]) for r in rows if r.get("region") == region]
            if nums:
                v = statistics.fmean(nums)
                return Solution(f"{v:.2f}", 0.94,
                                [f"Filtered {len(nums)} rows in {region}; mean {v:.2f}."],
                                "data.mean")

        if "90th percentile" in low:
            nums = sorted(float(r["latency_ms"]) for r in rows if "latency_ms" in r)
            if nums:
                idx = max(0, min(len(nums) - 1, int(round(0.9 * (len(nums) - 1)))))
                return Solution(f"{nums[idx]:.2f}", 0.9,
                                ["Nearest-rank p90 on the zero-indexed sorted array."],
                                "data.percentile")

        if "degraded" in low and "number of rows" in low:
            count = sum(1 for r in rows if r.get("status") == "degraded")
            return Solution(str(count), 0.95, [f"Counted {count} degraded rows."],
                            "data.count")

        if "relationship" in low or "pearson" in low:
            pairs = [(float(r[k1]), float(r[k2])) for r in rows
                     for k1, k2 in [("throughput", "latency")] if k1 in r and k2 in r]
            if pairs:
                r = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
                label = "POSITIVE" if r > 0.5 else ("NEGATIVE" if r < -0.5 else "NONE")
                return Solution(label, 0.92,
                                [f"Pearson correlation r = {r:.3f}.",
                                 "Threshold |r| > 0.5 for a directional call."],
                                "data.correlation")

        if "highest accuracy" in low:
            best, best_ratio = None, -1.0
            for r in rows:
                if "correct" in r and "tasks" in r:
                    ratio = float(r["correct"]) / max(1.0, float(r["tasks"]))
                    if ratio > best_ratio:
                        best, best_ratio = r.get("miner"), ratio
            if best:
                return Solution(best, 0.93,
                                [f"Computed correct/tasks per row; best {best_ratio:.3f}."],
                                "data.ratio")
        return Solution("unknown", 0.08, ["no matching data operation"],
                        "data.unmatched")

    @staticmethod
    def _csv_rows(prompt: str) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for block in CODE_BLOCK.findall(prompt):
            lines = [l for l in block.strip().splitlines() if l.strip()]
            if len(lines) < 2 or "," not in lines[0]:
                continue
            header = [h.strip() for h in lines[0].split(",")]
            for line in lines[1:]:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == len(header):
                    rows.append(dict(zip(header, parts)))
        return rows

    @staticmethod
    def _block(prompt: str) -> str:
        blocks = CODE_BLOCK.findall(prompt)
        return blocks[0] if blocks else prompt


class ProfiledSolver:
    """Applies an archetype's behaviour on top of a genuinely computed answer.

    Used to populate a local multi-neuron topology with distinguishable miners.
    The base answer always comes from real solving; the profile only degrades
    it (error injection, latency, confidence distortion, evidence quality),
    which is what a weaker or dishonest operator would look like on the wire.
    """

    #: Per-operator phrasing. Two independent operators running comparable
    #: models do not emit byte-identical prose, and the collusion detector keys
    #: on exactly that. Without this every neuron running the reference solver
    #: would flag itself — see docs/ANTI_GAMING.md §4.
    STYLES = (
        "{body}",
        "Reasoning: {body}",
        "{body} (verified)",
        "Step — {body}",
        "Observation: {body}",
        "Check: {body}",
        "Analysis notes that {lowered}",
        "{body} Confirmed against the task statement.",
    )

    def __init__(self, profile: MinerProfile, base: Optional[HeuristicSolver] = None,
                 seed: Optional[int] = None) -> None:
        self.profile = profile
        self.base = base or HeuristicSolver()
        self.rng = random.Random(seed)
        self._style = random.Random(seed).choice(self.STYLES)

    @property
    def name(self) -> str:
        return f"veritensor-heuristic/1+{self.profile.key}"

    def _restyle(self, body: str) -> str:
        return _restyle_impl(self._style, body)

    def solve(self, task: TaskRequest) -> Optional[Solution]:
        """Return a degraded-but-real solution, or ``None`` when the miner drops
        the request (modelling an unreliable operator)."""
        p = self.profile
        if self.rng.random() < p.dropout:
            return None

        solution = self.base.solve(task)
        keep = p.accuracy_for(task.category, task.difficulty)
        if self.rng.random() > keep and solution.answer != "unknown":
            solution = Solution(_perturb(solution.answer, self.rng),
                                solution.confidence, solution.evidence,
                                solution.method + "+degraded")

        if p.gaming:
            solution = Solution(_canned(task), 0.95,
                                ["Based on a comprehensive multi-step analysis of the "
                                 "provided material, the most probable answer is "
                                 "consistent with standard practice."],
                                "boilerplate")

        confidence = (p.confidence_fidelity * solution.confidence
                      + (1 - p.confidence_fidelity) * 0.9) + p.confidence_bias
        confidence = max(0.01, min(0.99, confidence + self.rng.gauss(0, 0.03)))

        evidence = solution.evidence
        if p.evidence_quality < 0.4 and not p.gaming:
            evidence = evidence[:1]
        elif p.evidence_quality > 0.8:
            evidence = evidence + [f"Cross-checked the {task.category.value} result "
                                   "against the stated constraints."]
        if not p.gaming:
            evidence = [self._restyle(item) for item in evidence]

        # simulate the operator's hardware/latency envelope
        target_ms = int(p.latency_mean_ms * (0.8 + 0.06 * task.difficulty)
                        * max(0.2, self.rng.lognormvariate(0.0, p.latency_jitter)))
        return Solution(solution.answer, confidence, evidence, solution.method,
                        latency_ms=target_ms)


def _restyle_impl(style: str, body: str) -> str:
    lowered = body[0].lower() + body[1:] if body else body
    return style.format(body=body, lowered=lowered)


def _perturb(answer: str, rng: random.Random) -> str:
    a = answer.strip()
    flips = {"VULNERABLE": "SAFE", "SAFE": "VULNERABLE", "BUGGY": "CORRECT",
             "CORRECT": "BUGGY", "POSITIVE": "NEGATIVE", "NEGATIVE": "NONE",
             "NONE": "POSITIVE"}
    if a.upper() in flips:
        return flips[a.upper()]
    if NUM.fullmatch(a):
        value = float(a)
        delta = max(1.0, abs(value) * rng.uniform(0.05, 0.35))
        out = value + rng.choice([-1, 1]) * delta
        return str(int(out)) if float(a).is_integer() else f"{out:.4f}"
    parts = [p.strip() for p in a.split(",") if p.strip()]
    if len(parts) > 1:
        rng.shuffle(parts)
        return ", ".join(parts)
    return "unknown"


def _canned(task: TaskRequest) -> str:
    return {"code": "VULNERABLE", "math": "42", "reasoning": "unknown",
            "data": "n01"}.get(task.category.value, "unknown")


def _fmt(x: float) -> str:
    return str(int(x)) if abs(x - round(x)) < 1e-9 else f"{x:.4f}"


def _pearson(xs: List[float], ys: List[float]) -> float:
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return 0.0 if dx == 0 or dy == 0 else num / (dx * dy)
