"""Generate a Kronaxis prediction for a UK council by-election.

For each upcoming by-election:
  1. Build vote-share prior: last result + recent national swing
  2. Run KPM-2.2 v15.1 fragmentation override
  3. Hash the prediction
  4. Append to public scorecard

Vote-share prior uses Uniform National Swing (UNS) as the baseline since
ward-level swing models come in Week 4. This is honest: we publish the
swing assumption alongside the prediction so anyone can challenge it.

Usage:
  python3 -m scripts.byelection.predict --council "Bradford" --ward "Wibsey" \
    --election-date 2026-05-15 --incumbent Labour \
    --last-shares "Lab=45.2,Con=22.1,Reform=12.0,LD=10.0,Green=10.7"
"""
from __future__ import annotations
import argparse, json, sys, hashlib, subprocess
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.kpm2.classify import apply_fragmentation_override, Classification
from scripts.kpm2.rules import FRAGMENTATION_RULE, fragmentation_hash

# UNS swings (in pp) since last full election cycle. Updated periodically
# from polling aggregator (Wikipedia: Opinion polling for the next UK GE).
# This is the public assumption — anyone can challenge the choice of swings.
NATIONAL_SWING_2024_TO_2026 = {
    'Labour': -10.0,        # 2024 GE Lab share ~34%, 2026 polling ~24%
    'Conservative': -8.0,   # 2024 GE ~24%, 2026 polling ~16%
    'Reform UK': +12.0,     # 2024 GE ~14%, 2026 polling ~26%
    'Liberal Democrat': +1.0,
    'Green': +3.0,
    'Independent': +1.0,
    'Other': 0.0,
}

PARTY_NORMALISE = {
    'Lab':'Labour','Con':'Conservative','LD':'Liberal Democrat','Lib Dem':'Liberal Democrat',
    'Reform':'Reform UK','RefUK':'Reform UK','Grn':'Green','Ind':'Independent',
}
def cn(p): return PARTY_NORMALISE.get(p, p)

def parse_shares(s):
    out = {}
    for kv in s.split(','):
        if '=' not in kv: continue
        k, v = kv.split('=', 1)
        out[k.strip()] = float(v.strip())
    return out

def apply_uns(last_shares, swings):
    """Apply Uniform National Swing to last-result shares; renormalise to 100."""
    new = {}
    for p, s in last_shares.items():
        canon = cn(p)
        new[canon] = max(0.0, s + swings.get(canon, swings.get('Other', 0.0)))
    total = sum(new.values()) or 1
    return {k: round(100 * v / total, 2) for k, v in new.items()}

def build_prediction(args):
    last_shares = parse_shares(args.last_shares)
    if not last_shares:
        print("ERROR: no last_shares parsed", file=sys.stderr)
        sys.exit(1)
    projected = apply_uns(last_shares, NATIONAL_SWING_2024_TO_2026)
    print(f"Last result shares:    {last_shares}")
    print(f"Applied swing 2024-26: {NATIONAL_SWING_2024_TO_2026}")
    print(f"Projected vote shares: {projected}")

    # Run v15.1 fragmentation
    sorted_s = sorted(projected.items(), key=lambda kv: -kv[1])
    top_party = sorted_s[0][0]
    margin = sorted_s[0][1] - (sorted_s[1][1] if len(sorted_s) > 1 else 0)
    base = Classification(top_party, "Lean", margin, False, "uns_2024_to_2026")
    cls = apply_fragmentation_override(projected, base,
        region=args.region, council_type=args.council_type or '',
        incumbent=args.incumbent, council_name=args.council)
    print(f"v15.1 prediction: {cls.predicted_winner} ({cls.confidence}, margin {cls.margin_pp:.1f}pp)")
    print(f"v15.1 cassette tags: {cls.cassette_name}")

    # Build scorecard entry
    pred_id = f"kpm22-v15-1-byel-{args.election_date}-{args.council.lower().replace(' ','-')}-{args.ward.lower().replace(' ','-')}"
    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

    entry = {
        'id': pred_id,
        'kind': 'uk_council_byelection',
        'election_id': f'byel-{args.election_date}-{args.council.lower().replace(" ","-")}-{args.ward.lower().replace(" ","-")}',
        'election_date': args.election_date,
        'subject': f"{args.council} - {args.ward}",
        'subject_council': args.council,
        'subject_ward': args.ward,
        'subject_id': f'byel-{args.council.lower().replace(" ","-")}-{args.ward.lower().replace(" ","-")}',
        'region': args.region,
        'council_type': args.council_type or 'unknown',
        'incumbent_before': args.incumbent,
        'predicted_winner': cls.predicted_winner,
        'predicted_confidence': cls.confidence,
        'predicted_margin_pp': round(float(cls.margin_pp), 2),
        'vote_shares_predicted': projected,
        'vote_shares_last_result': last_shares,
        'national_swing_assumed': NATIONAL_SWING_2024_TO_2026,
        'predicted_at': now_iso,
        'methodology': {
            'name': 'KPM-2.2',
            'version': 'v15.1',
            'hash_sha256': fragmentation_hash(),
            'commit': git_head(),
            'code_url': f'https://github.com/Kronaxis/kpm/tree/{git_head()}/scripts/kpm2/',
            'prior_method': 'last-result + UNS_2024_to_2026',
        },
    }
    return entry

def git_head():
    try:
        out = subprocess.run(['git','rev-parse','HEAD'], cwd=REPO, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return 'unknown'

def append_to_scorecard(entry):
    """Append the prediction to the public scorecard (idempotent on id)."""
    sc_path = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'
    sc = json.loads(sc_path.read_text())
    existing_ids = {p['id'] for p in sc['predictions']}
    if entry['id'] in existing_ids:
        print(f"NOTE: prediction {entry['id']} already in scorecard - skipping append")
        return False
    sc['predictions'].append(entry)
    sc['last_updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    sc_path.write_text(json.dumps(sc, indent=2))
    print(f"Appended {entry['id']} to {sc_path}")
    return True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--council', required=True)
    ap.add_argument('--ward', required=True)
    ap.add_argument('--election-date', required=True, help='YYYY-MM-DD')
    ap.add_argument('--incumbent', required=True, help='Outgoing councillor party')
    ap.add_argument('--region', required=True, help='e.g. "North West"')
    ap.add_argument('--council-type', default='', help='Optional: metropolitan_boroughs / london_boroughs / etc.')
    ap.add_argument('--last-shares', required=True, help='e.g. "Lab=45.2,Con=22.1,Reform=12.0,LD=10.0,Green=10.7"')
    ap.add_argument('--no-append', action='store_true', help="Don't append to scorecard (dry-run)")
    args = ap.parse_args()

    entry = build_prediction(args)
    print(f"\nPrediction id: {entry['id']}")
    print(f"Methodology hash: {entry['methodology']['hash_sha256']}")
    print(f"Git commit: {entry['methodology']['commit']}")

    if not args.no_append:
        append_to_scorecard(entry)
        print("\nNext: rerun scripts/scorecard/refresh.sh to recompute metrics + publish to website")

if __name__ == '__main__':
    main()
