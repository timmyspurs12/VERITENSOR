"""Read-only testnet preflight.

Checks every prerequisite for a real Bittensor run without signing or
submitting anything. Exit code 0 means "ready to submit weights"; any other
code means at least one prerequisite is missing, and the report says which.

    python -m scripts.preflight
    python -m scripts.preflight --netuid 429 --network test --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from subnet.adapters.bittensor_adapter import BittensorAdapter  # noqa: E402
from subnet.chain.sdk import probe  # noqa: E402

TICK = {True: "\033[32m✓\033[0m", False: "\033[31m✗\033[0m"}

ADVICE = {
    "sdk_installed": "pip install -r requirements-bittensor.txt",
    "sdk_supported": "pip install -U bittensor  (VERITENSOR targets the v11 API)",
    "netuid_configured": "set SUBNET_NETUID in .env after choosing/creating a subnet",
    "chain_reachable": "check network access to the configured endpoint",
    "subnet_exists": "btcli subnet list --subtensor.network test",
    "wallet_files_present": ("btcli wallet new_coldkey --wallet.name <NAME> && "
                             "btcli wallet new_hotkey --wallet.name <NAME> "
                             "--wallet.hotkey <HOTKEY>"),
    "hotkey_registered": ("btcli subnet register --netuid <NETUID> "
                          "--wallet.name <NAME> --wallet.hotkey <HOTKEY> "
                          "--subtensor.network test   (burns TAO)"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="VERITENSOR testnet preflight (read-only)")
    ap.add_argument("--netuid", type=int, default=None)
    ap.add_argument("--network", default=None)
    ap.add_argument("--wallet", default=None)
    ap.add_argument("--hotkey", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    adapter = BittensorAdapter(
        netuid=args.netuid if args.netuid is not None
        else int(os.getenv("SUBNET_NETUID", "0")),
        network=args.network or os.getenv("BITTENSOR_NETWORK", "test"),
        wallet_name=args.wallet, hotkey_name=args.hotkey)
    report = adapter.preflight()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0 if report.get("ready_to_submit_weights") else 1

    caps = probe()
    print("\nVERITENSOR — testnet preflight (read-only)\n")
    print(f"  SDK        bittensor {caps.version or 'not installed'} ({caps.generation})")
    print(f"  network    {report['network']}")
    print(f"  netuid     {report['netuid'] or '(unset)'}")
    print(f"  wallet     {report['wallet']['name'] or '(unset)'}"
          f"/{report['wallet']['hotkey'] or '(unset)'}")
    if "block" in report:
        print(f"  block      {report['block']}")
    if "subnet" in report:
        s = report["subnet"]
        print(f"  subnet     {s.get('name')}  uids {s.get('num_uids')}/{s.get('max_uids')}"
              f"  tempo {s.get('tempo')}")
    if "registration_cost" in report:
        print(f"  burn cost  {report['registration_cost']}")
    if report.get("uid") is not None:
        print(f"  your uid   {report['uid']}")
    print("\n  Checks")
    for name, ok in report["checks"].items():
        line = f"    {TICK[bool(ok)]} {name}"
        if not ok and name in ADVICE:
            line += f"\n        → {ADVICE[name]}"
        print(line)
    for key in ("chain_error", "subnet_error", "wallet_error"):
        if key in report:
            print(f"\n  {key}: {report[key]}")

    ready = bool(report.get("ready_to_submit_weights"))
    print(f"\n  {'READY' if ready else 'NOT READY'} to submit weights on chain.\n")
    if not ready:
        print("  Nothing above was fabricated: every ✗ is a real, outstanding\n"
              "  prerequisite. See docs/DEPLOYMENT_CHECKLIST.md.\n")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
