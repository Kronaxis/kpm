"""KPM-2 pre-registration helper.

Generates the pre-registration manifest (hash receipt for all 3 cassettes
plus the calibration default), writes it to a file, and verifies that the
on-disk manifest matches the live cassette code.

Idempotency: re-running should produce identical hashes given identical
cassette code. Any drift between live code and the previously-committed
manifest = a falsifiability violation we must own publicly.

Usage:
  python3 -m scripts.kpm2.prereg --write data/kpm2_prereg_manifest.json
  python3 -m scripts.kpm2.prereg --verify data/kpm2_prereg_manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .rules import CASSETTES, manifest as cassette_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "data" / "kpm2_prereg_manifest.json"
CALIBRATION_DEFAULT_PATH = REPO_ROOT / "data" / "kpm2_calibration_default.json"
METHODOLOGY_PATH = REPO_ROOT / "docs" / "KPM2_METHODOLOGY.md"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(
    include_calibration: bool = True,
    include_methodology: bool = True,
    phase5_results_path: Path | None = None,
) -> dict:
    """Assemble the full pre-reg manifest."""
    m = cassette_manifest()
    out = {
        "schema_version": "kpm2-prereg-v1",
        "kpm2_version": _read_version(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cassettes": m,
    }
    if include_calibration and CALIBRATION_DEFAULT_PATH.exists():
        cal = json.loads(CALIBRATION_DEFAULT_PATH.read_text())
        cal_canonical = json.dumps(cal, sort_keys=True).encode("utf-8")
        out["calibration_default"] = {
            "hash_sha256": hashlib.sha256(cal_canonical).hexdigest(),
            "as_of": cal.get("as_of"),
            "half_life_days": cal.get("half_life_days"),
        }
    if include_methodology and METHODOLOGY_PATH.exists():
        out["methodology"] = {
            "path": str(METHODOLOGY_PATH.relative_to(REPO_ROOT)),
            "hash_sha256": _hash_file(METHODOLOGY_PATH),
            "byte_count": METHODOLOGY_PATH.stat().st_size,
        }
    if phase5_results_path and phase5_results_path.exists():
        results = json.loads(phase5_results_path.read_text())
        scoring = results.get("scoring", {})
        abs_path = phase5_results_path.resolve()
        try:
            display_path = str(abs_path.relative_to(REPO_ROOT.resolve()))
        except ValueError:
            display_path = str(phase5_results_path)
        out["phase5_validation"] = {
            "path": display_path,
            "hash_sha256": _hash_file(phase5_results_path),
            "cassette": results.get("cassette"),
            "panel_size": results.get("panel_size"),
            "llm_model": results.get("llm_model"),
            "scoring": scoring,
        }
    return out


def _read_version() -> str:
    init_path = REPO_ROOT / "scripts" / "kpm2" / "__init__.py"
    for line in init_path.read_text().splitlines():
        if line.startswith("__version__"):
            return line.split("=")[1].strip().strip("\"'")
    return "unknown"


def write_manifest(path: Path) -> None:
    m = build_manifest()
    path.write_text(json.dumps(m, indent=2, sort_keys=False))
    print(f"Wrote {path}")
    print(f"  Cassettes: {list(CASSETTES.keys())}")
    print(f"  Combined cassette hash: {m['cassettes']['combined_hash_sha256']}")
    if "calibration_default" in m:
        print(f"  Calibration hash: {m['calibration_default']['hash_sha256']}")


def verify_manifest(path: Path) -> int:
    """Return exit code: 0 = match, 1 = drift, 2 = file missing."""
    if not path.exists():
        print(f"ERROR: manifest not found at {path}", file=sys.stderr)
        return 2
    on_disk = json.loads(path.read_text())
    live = build_manifest()

    # Check each cassette individually
    on_disk_cassettes = on_disk.get("cassettes", {}).get("cassettes", {})
    live_cassettes = live["cassettes"]["cassettes"]

    drift = []
    for name in set(on_disk_cassettes) | set(live_cassettes):
        d = on_disk_cassettes.get(name, {}).get("hash_sha256")
        l = live_cassettes.get(name, {}).get("hash_sha256")
        if d != l:
            drift.append((name, d, l))

    if drift:
        print(f"\nDRIFT DETECTED — {len(drift)} cassette(s) differ from pre-reg:", file=sys.stderr)
        for name, d, l in drift:
            print(f"  {name}", file=sys.stderr)
            print(f"    pre-reg hash:  {d}", file=sys.stderr)
            print(f"    live hash:     {l}", file=sys.stderr)
        return 1

    # Check combined hash
    on_disk_combined = on_disk.get("cassettes", {}).get("combined_hash_sha256")
    live_combined = live["cassettes"]["combined_hash_sha256"]
    if on_disk_combined != live_combined:
        print("\nDRIFT: combined hash mismatch", file=sys.stderr)
        print(f"  pre-reg: {on_disk_combined}", file=sys.stderr)
        print(f"  live:    {live_combined}", file=sys.stderr)
        return 1

    print(f"\nVERIFIED — all {len(live_cassettes)} cassettes match pre-reg")
    print(f"  Combined hash: {live_combined}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", help="Write manifest to this path")
    g.add_argument("--verify", help="Verify manifest at this path matches live code")
    g.add_argument("--print", action="store_true", help="Print manifest to stdout (no write)")
    parser.add_argument("--phase5", help="Path to phase5 validation results JSON to embed")
    args = parser.parse_args()

    phase5_path = Path(args.phase5) if args.phase5 else None

    if args.print:
        print(json.dumps(build_manifest(phase5_results_path=phase5_path), indent=2))
        return 0
    if args.write:
        out_path = Path(args.write)
        m = build_manifest(phase5_results_path=phase5_path)
        out_path.write_text(json.dumps(m, indent=2, sort_keys=False))
        print(f"Wrote {out_path}")
        print(f"  Cassettes: combined hash {m['cassettes']['combined_hash_sha256']}")
        if "methodology" in m:
            print(f"  Methodology hash: {m['methodology']['hash_sha256']}")
        if "phase5_validation" in m:
            s = m["phase5_validation"]["scoring"]
            print(f"  Phase 5 validation: KPM-2 {s.get('kpm2_hits')}/{s.get('n')} vs KPM-1 {s.get('kpm1_hits')}/{s.get('n')}")
        return 0
    if args.verify:
        return verify_manifest(Path(args.verify))
    return 0


if __name__ == "__main__":
    sys.exit(main())
