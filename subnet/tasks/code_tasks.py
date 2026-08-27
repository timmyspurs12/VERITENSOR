"""Code verification tasks.

Every snippet is assembled from parameterised templates so that the *text* of
the task differs on every draw while the hidden verdict stays programmatically
known. Output-prediction tasks are graded by actually executing the reference
implementation inside a restricted namespace at generation time — the ground
truth is computed, never hand-written.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from ..protocol.messages import Category, VerificationType
from .base import BaseGenerator, GeneratedTask, GroundTruth, register

_IDENT_POOL = [
    ("user_id", "account_id"), ("conn", "db"), ("cur", "cursor"),
    ("query", "sql"), ("rows", "records"), ("data", "payload"),
    ("name", "label"), ("items", "elements"), ("total", "acc"),
    ("result", "out"), ("path", "filepath"), ("cmd", "command"),
]

_TABLES = ["users", "accounts", "orders", "sessions", "invoices", "devices",
           "audits", "payments", "tenants", "api_keys", "webhooks", "reports",
           "shipments", "subscriptions", "workspaces", "credentials"]
_COLS = ["email", "status", "role", "region", "tier", "handle", "slug",
         "reference", "external_id", "label", "channel", "locale"]
_FNS_DB = ["fetch_user", "lookup_record", "get_row", "load_entity",
           "find_one", "select_entry", "resolve_actor", "read_document"]
_FNS_BUG = ["last_index", "window_sum", "tail_slice", "prefix_total",
            "rolling_sum", "bucket_count", "accumulate", "fold_left"]
_ACCUMULATORS = ["acc", "total", "running", "aggregate", "carry"]
_SEQUENCES = ["xs", "values", "items", "samples", "rows", "buffer"]


# --------------------------------------------------------------------------
# snippet builders: each returns (code, is_vulnerable, cwe, keywords)
# --------------------------------------------------------------------------
def _sql_snippet(rng: random.Random, vulnerable: bool) -> Tuple[str, List[str]]:
    table = rng.choice(_TABLES)
    col = rng.choice(_COLS)
    fn = rng.choice(_FNS_DB)
    limit = rng.randint(10, 500)
    order = rng.choice(["id", "created_at", "updated_at"])
    if vulnerable:
        style = rng.choice(["concat", "percent", "fstring"])
        if style == "concat":
            expr = f'"SELECT id, {col} FROM {table} WHERE {col} = \'" + {col} + "\'"'
        elif style == "percent":
            expr = f'"SELECT id, {col} FROM {table} WHERE {col} = \'%s\'" % {col}'
        else:
            expr = f'f"SELECT id, {col} FROM {table} WHERE {col} = \'{{{col}}}\'"'
        body = (f"    query = {expr}\n"
                f'    query += " ORDER BY {order} LIMIT {limit}"\n'
                f"    cur.execute(query)\n")
    else:
        body = (
            f'    query = "SELECT id, {col} FROM {table} WHERE {col} = ? '
            f'ORDER BY {order} LIMIT {limit}"\n'
            f"    cur.execute(query, ({col},))\n"
        )
    code = (
        f"def {fn}(conn, {col}):\n"
        f"    cur = conn.cursor()\n"
        f"{body}"
        f"    return cur.fetchall()\n"
    )
    return code, ["string concatenation", "parameterized query", "sql injection", "cwe-89"]


def _cmd_snippet(rng: random.Random, vulnerable: bool) -> Tuple[str, List[str]]:
    tool = rng.choice(["ping", "convert", "gzip", "curl", "traceroute", "dig",
                       "ffmpeg", "rsync", "openssl"])
    count = rng.randint(1, 9)
    if vulnerable:
        body = (f'    os.system(f"{tool} -c {count} {{target}}")\n'
                if rng.random() < 0.5 else
                f'    subprocess.run(f"{tool} -c {count} {{target}}", shell=True)\n')
    else:
        body = (f'    subprocess.run(["{tool}", "-c", "{count}", target], '
                f"check=True, shell=False)\n")
    code = (
        "import os, subprocess\n\n"
        f"def run_probe(target):\n"
        f"{body}"
        "    return True\n"
    )
    return code, ["shell", "os.system", "argument list", "command injection", "cwe-78"]


def _path_snippet(rng: random.Random, vulnerable: bool) -> Tuple[str, List[str]]:
    root = rng.choice(["/srv/uploads", "/var/data", "/opt/files", "/mnt/assets",
                       "/srv/tenant/blobs", "/var/lib/veritensor/artifacts",
                       "/opt/cache/objects", "/data/exports"])
    fn = rng.choice(["read_asset", "load_blob", "fetch_artifact", "open_export",
                     "serve_file", "get_object"])
    encoding = rng.choice(["utf-8", "utf-8", "latin-1"])
    if vulnerable:
        body = (f'    full = os.path.join("{root}", name)\n'
                f'    return open(full, encoding="{encoding}").read()\n')
    else:
        body = (
            f'    base = os.path.realpath("{root}")\n'
            "    full = os.path.realpath(os.path.join(base, name))\n"
            "    if not full.startswith(base + os.sep):\n"
            "        raise ValueError('path escape')\n"
            f'    return open(full, encoding="{encoding}").read()\n'
        )
    code = f"import os\n\ndef {fn}(name):\n" + body
    return code, ["path traversal", "realpath", "../", "cwe-22"]


def _crypto_snippet(rng: random.Random, vulnerable: bool) -> Tuple[str, List[str]]:
    fn = rng.choice(["store_password", "hash_secret", "derive_key",
                     "persist_credential", "digest_password"])
    iterations = rng.choice([120_000, 200_000, 240_000, 310_000, 480_000])
    if vulnerable:
        algo = rng.choice(["md5", "sha1"])
        style = rng.choice(["plain", "salted_concat"])
        arg = "password.encode()" if style == "plain" else "(password + salt).encode()"
        body = f"    return hashlib.{algo}({arg}).hexdigest()\n"
    else:
        prf = rng.choice(["sha256", "sha512"])
        body = ("    return hashlib.pbkdf2_hmac("
                f"'{prf}', password.encode(), salt, {iterations}).hex()\n")
    code = f"import hashlib\n\ndef {fn}(password, salt):\n" + body
    return code, ["md5", "pbkdf2", "salt", "weak hash", "cwe-327"]


_VULN_BUILDERS = [_sql_snippet, _cmd_snippet, _path_snippet, _crypto_snippet]


@register
class VulnerabilityDetectionGenerator(BaseGenerator):
    """Given a snippet, decide whether it contains the named vulnerability class."""

    name = "code.vulnerability"
    category = Category.CODE
    verification_type = VerificationType.PROGRAMMATIC
    default_timeout_s = 25

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        vulnerable = rng.random() < 0.5
        builder = rng.choice(_VULN_BUILDERS)
        code, keywords = builder(rng, vulnerable)
        if difficulty >= 6:
            code = _add_distractors(code, rng, hard=difficulty >= 8)
        prompt = (
            "Analyse the following Python snippet for security defects.\n\n"
            "```python\n" + code + "```\n\n"
            "Answer with exactly one word: VULNERABLE or SAFE. "
            "In `evidence`, name the defect class (or justify why the code is safe)."
        )
        gt = GroundTruth(
            answer="vulnerable" if vulnerable else "safe",
            verifier="boolean",
            evidence_keywords=keywords,
            explanation=(
                "Vulnerable pattern present." if vulnerable
                else "Uses the safe/parameterised construct."
            ),
        )
        req = self.build_request(
            prompt, difficulty,
            answer_schema={"type": "enum", "values": ["VULNERABLE", "SAFE"]},
        )
        return GeneratedTask(
            request=req, ground_truth=gt, generator=self.name,
            mutation_spec={"kind": "code", "code": code, "builder": builder.__name__,
                           "vulnerable": vulnerable, "keywords": keywords},
        )

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        spec = task.mutation_spec
        if spec.get("kind") != "code":
            return None
        mutated = _mutate_code(spec["code"], rng)
        prompt = (
            "Analyse the following Python snippet for security defects.\n\n"
            "```python\n" + mutated + "```\n\n"
            "Answer with exactly one word: VULNERABLE or SAFE."
        )
        req = self.build_request(
            prompt, task.request.difficulty,
            verification_type=VerificationType.ADVERSARIAL,
            parent_task_id=task.request.task_id,
        )
        gt = GroundTruth(
            answer=task.ground_truth.answer, verifier="boolean",
            evidence_keywords=task.ground_truth.evidence_keywords,
            explanation="Semantics-preserving mutation of " + task.request.task_id,
        )
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={**spec, "code": mutated})


@register
class OutputPredictionGenerator(BaseGenerator):
    """Predict the return value of a generated function (executed for truth)."""

    name = "code.output_prediction"
    category = Category.CODE
    verification_type = VerificationType.PROGRAMMATIC
    default_timeout_s = 25

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        n = rng.randint(4, 6 + difficulty)
        start = rng.randint(1, 9)
        step = rng.randint(2, 3 + difficulty // 2)
        mod = rng.choice([7, 9, 11, 13])
        code = (
            "def compute():\n"
            f"    total = {start}\n"
            f"    for i in range(1, {n}):\n"
            f"        if i % 2 == 0:\n"
            f"            total += i * {step}\n"
            "        else:\n"
            f"            total -= i\n"
            f"    return total % {mod}\n"
        )
        value = _exec_compute(code)
        prompt = (
            "Predict the exact integer returned by `compute()` without running it.\n\n"
            "```python\n" + code + "```\n\nAnswer with the integer only."
        )
        gt = GroundTruth(
            answer=str(value), verifier="numeric", params={"atol": 0.0, "rtol": 0.0},
            evidence_keywords=["loop", "modulo", "iteration", "trace"],
            explanation=f"Executed reference implementation returns {value}.",
        )
        req = self.build_request(prompt, difficulty, answer_schema={"type": "integer"})
        return GeneratedTask(
            request=req, ground_truth=gt, generator=self.name,
            mutation_spec={"kind": "output", "code": code, "value": value},
        )

    def mutate(self, task: GeneratedTask, rng: random.Random) -> Optional[GeneratedTask]:
        spec = task.mutation_spec
        if spec.get("kind") != "output":
            return None
        # rename identifiers + inject no-op statements; value must not change
        mutated = _mutate_code(spec["code"], rng)
        value = _exec_compute(mutated)
        if value != spec["value"]:  # mutation was not semantics preserving
            return None
        prompt = (
            "Predict the exact integer returned by `compute()`.\n\n"
            "```python\n" + mutated + "```\n\nAnswer with the integer only."
        )
        req = self.build_request(
            prompt, task.request.difficulty,
            verification_type=VerificationType.ADVERSARIAL,
            parent_task_id=task.request.task_id,
        )
        gt = GroundTruth(answer=str(value), verifier="numeric",
                         params={"atol": 0.0, "rtol": 0.0},
                         explanation="Mutation preserves the return value.")
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={**spec, "code": mutated})


@register
class BugDetectionGenerator(BaseGenerator):
    """Off-by-one / boundary bug detection with programmatic verdict."""

    name = "code.bug_detection"
    category = Category.CODE
    verification_type = VerificationType.PROGRAMMATIC

    def generate(self, difficulty: int, rng: random.Random) -> GeneratedTask:
        buggy = rng.random() < 0.5
        fn = rng.choice(_FNS_BUG)
        acc = rng.choice(_ACCUMULATORS)
        seq = rng.choice(_SEQUENCES)
        start = rng.choice([0, 0, 1])
        weight = rng.randint(1, 9)
        if buggy:
            bound = rng.choice([f"len({seq}) + 1", f"len({seq}) + 2"])
        else:
            bound = rng.choice([f"len({seq})", f"len({seq}) - 0"])
        op = rng.choice([f"{acc} += {seq}[i]",
                         f"{acc} += {seq}[i] * {weight}",
                         f"{acc} = {acc} + {seq}[i]"])
        code = (f"def {fn}({seq}):\n"
                f"    {acc} = {start}\n"
                f"    for i in range({bound}):\n"
                f"        {op}\n"
                f"    return {acc}\n")
        prompt = (
            "Does the function below raise an exception for a non-empty list "
            "(i.e. does it contain an out-of-range bug)?\n\n"
            "```python\n" + code + "```\n\nAnswer BUGGY or CORRECT."
        )
        gt = GroundTruth(
            answer="buggy" if buggy else "correct", verifier="boolean",
            evidence_keywords=["index", "range", "len", "off-by-one", "indexerror"],
            explanation="range(len(xs)+1) overruns the list." if buggy
            else "Iteration bounds are correct.",
        )
        req = self.build_request(prompt, difficulty,
                                 answer_schema={"type": "enum",
                                                "values": ["BUGGY", "CORRECT"]})
        return GeneratedTask(request=req, ground_truth=gt, generator=self.name,
                             mutation_spec={"kind": "code", "code": code,
                                            "vulnerable": buggy})

    mutate = VulnerabilityDetectionGenerator.mutate  # same textual mutation strategy


# --------------------------------------------------------------------------
# mutation helpers
# --------------------------------------------------------------------------
def _mutate_code(code: str, rng: random.Random) -> str:
    """Semantics-preserving textual mutation: renames, comments, whitespace."""
    out = code
    for old, new in rng.sample(_IDENT_POOL, k=min(3, len(_IDENT_POOL))):
        out = _rename(out, old, new)
    if rng.random() < 0.7:
        lines = out.splitlines()
        insert_at = 0
        lines.insert(insert_at, f"# revision {rng.randint(100, 999)} - refactor, no behaviour change")
        out = "\n".join(lines) + "\n"
    if rng.random() < 0.5:
        out = out.replace("def ", "def  ", 1).replace("def  ", "def ", 1)
    return out


def _rename(code: str, old: str, new: str) -> str:
    import re

    return re.sub(rf"\b{re.escape(old)}\b", new, code)


def _add_distractors(code: str, rng: random.Random, hard: bool) -> str:
    extras = [
        "    # NOTE: input is validated upstream by the API gateway\n",
        "    logger.debug('entering handler')\n",
        "    metrics.increment('db.query')\n",
    ]
    lines = code.splitlines(keepends=True)
    idx = min(len(lines) - 1, 1)
    chosen = rng.sample(extras, k=2 if hard else 1)
    for extra in chosen:
        lines.insert(idx, extra)
    prefix = "import logging\nlogger = logging.getLogger(__name__)\n\n" if hard else ""
    return prefix + "".join(lines)


def _exec_compute(code: str) -> int:
    """Execute a validator-authored snippet in a restricted namespace."""
    env: Dict[str, Any] = {"__builtins__": {"range": range, "len": len}}
    exec(compile(code, "<generated>", "exec"), env)  # noqa: S102 - validator-authored
    return int(env["compute"]())
