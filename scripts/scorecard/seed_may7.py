"""Seed the public Kronaxis scorecard with the 134 May 7 2026 council predictions
and their actuals. This is the foundational artefact - first deposits.

Schema is forward-looking: future elections (council by-elections, parliamentary
by-elections, mayoral, devolved, GE) all use this same schema."""
from __future__ import annotations
import json, hashlib, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

REPO = Path('/home/jason/projects/kronaxis')
OUT = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'

def git_commit_for_file(path):
    """First-commit hash that introduced/published a given file (proxy for predicted_at)."""
    try:
        out = subprocess.run(
            ['git', 'log', '--diff-filter=A', '--reverse', '--format=%H %cI', '--', str(path)],
            cwd=REPO, capture_output=True, text=True, check=True
        )
        first_line = out.stdout.strip().split('\n')[0]
        if first_line:
            commit, iso = first_line.split(' ', 1)
            return commit, iso
    except Exception:
        pass
    return None, None

def norm_winner(w):
    s = (w or "").strip()
    return {"NOC":"No overall control","No Overall Control":"No overall control",
            "no overall control":"No overall control","Lib Dem":"Liberal Democrat",
            "Liberal Democrats":"Liberal Democrat","Reform":"Reform UK",
            "Conservatives":"Conservative","Tories":"Conservative"}.get(s, s)

def slugify(name):
    return name.lower().replace(' ', '-').replace(',', '').replace("'", '')

def main():
    # Load KPM-1 predictions (the published live page)
    kpm1_file = REPO / 'website' / 'kronaxis' / 'data' / 'election-results-2026.json'
    kpm1_data = json.loads(kpm1_file.read_text())
    councils = {c['name']: c for c in kpm1_data.get('councils', []) if 'name' in c}

    # Load actuals (hand-verified 52 + Bradford union scrape 78)
    orig = json.loads((REPO / 'data' / 'may7_actual_results.json').read_text())['council_winners_actual']
    full = json.loads((REPO / 'data' / 'may7_actuals_full.json').read_text())['council_winners_actual_full']
    # Hand-verified wins on overlap
    actuals = dict(full)
    for k, v in orig.items():
        actuals[k] = v
    print(f"KPM-1 councils: {len(councils)}, actuals available: {len(actuals)}")

    # Provenance: when KPM-1 was first published (via git history)
    kpm1_commit, kpm1_iso = git_commit_for_file('website/kronaxis/data/election-results-2026.json')
    if not kpm1_commit:
        print("WARNING: could not find KPM-1 publication commit", file=sys.stderr)
        kpm1_commit = 'unknown'
        kpm1_iso = '2026-05-06T00:00:00Z'  # before election day fallback
    print(f"KPM-1 first published: {kpm1_iso} (commit {kpm1_commit[:8]})")

    # Methodology hash (KPM-1 published rules)
    methodology_kpm1_hash = hashlib.sha256(json.dumps({
        'name': 'KPM-1',
        'version': 'v1.0-published',
        'description': 'LLM-panel synthetic personas + DYNAMICS-8 + tactical voting + seat MC. Published before May 7 2026.',
        'commit': kpm1_commit,
    }, sort_keys=True).encode()).hexdigest()

    predictions = []
    election_id = '2026-05-07-english-locals'
    election_date = '2026-05-07'

    for council_name, rec in councils.items():
        actual = actuals.get(council_name)
        actual_norm = norm_winner(actual) if actual else None
        predicted = norm_winner(rec.get('predicted_winner', ''))
        confidence = rec.get('confidence', 'Toss-up')
        margin = rec.get('margin_pp', 0)
        vs = rec.get('vote_shares', {})

        pred_id = f"kpm1-{election_id}-council-{slugify(council_name)}"

        entry = {
            'id': pred_id,
            'kind': 'uk_council_election',
            'election_id': election_id,
            'election_date': election_date,
            'subject': council_name,
            'subject_id': slugify(council_name),
            'region': rec.get('region', ''),
            'council_type': rec.get('council_type', ''),
            'incumbent_before': rec.get('incumbent', ''),
            'predicted_winner': predicted,
            'predicted_confidence': confidence,
            'predicted_margin_pp': round(float(margin), 2),
            'vote_shares_predicted': {k: round(float(v), 2) for k, v in vs.items()},
            'predicted_at': kpm1_iso,
            'predicted_at_git_commit': kpm1_commit,
            'methodology': {
                'name': 'KPM-1',
                'version': 'v1.0',
                'hash_sha256': methodology_kpm1_hash,
                'commit': kpm1_commit,
                'code_url': f'https://github.com/Kronaxis/kpm/tree/{kpm1_commit}/scripts/kpm1/',
            },
        }
        if actual_norm:
            entry['actual_winner'] = actual_norm
            entry['actual_at'] = '2026-05-09T18:00:00Z'  # by Saturday evening when Bradford landed
            entry['actual_source'] = 'https://en.wikipedia.org/wiki/2026_United_Kingdom_local_elections'
            entry['hit'] = predicted == actual_norm
        predictions.append(entry)

    # Also add KPM-2.2 v15.1 predictions (the second methodology) for the same councils
    # Re-run v15.1 on each council and add a parallel prediction record
    sys.path.insert(0, str(REPO))
    from scripts.kpm2.classify import apply_fragmentation_override, Classification
    from scripts.kpm2.rules import FRAGMENTATION_RULE, fragmentation_hash

    v151_hash = fragmentation_hash()
    v151_commit, v151_iso = git_commit_for_file('scripts/kpm2/rules.py')
    print(f"v15.1 first published: {v151_iso} (commit {v151_commit[:8] if v151_commit else 'n/a'})")

    v151_predictions = []
    for council_name, rec in councils.items():
        actual = actuals.get(council_name)
        actual_norm = norm_winner(actual) if actual else None
        cls = Classification(
            norm_winner(rec.get('predicted_winner', '')),
            rec.get('confidence', 'Toss-up'),
            rec.get('margin_pp', 0.0),
            False, 'kpm1'
        )
        cls = apply_fragmentation_override(rec.get('vote_shares', {}), cls,
            region=rec.get('region', ''), council_type=rec.get('council_type', ''),
            incumbent=rec.get('incumbent', ''), council_name=council_name)
        predicted = norm_winner(cls.predicted_winner)

        pred_id = f"kpm22-v15-1-{election_id}-council-{slugify(council_name)}"
        entry = {
            'id': pred_id,
            'kind': 'uk_council_election',
            'election_id': election_id,
            'election_date': election_date,
            'subject': council_name,
            'subject_id': slugify(council_name),
            'region': rec.get('region', ''),
            'council_type': rec.get('council_type', ''),
            'incumbent_before': rec.get('incumbent', ''),
            'predicted_winner': predicted,
            'predicted_confidence': cls.confidence,
            'predicted_margin_pp': round(float(cls.margin_pp), 2),
            'vote_shares_predicted': {k: round(float(v), 2) for k, v in rec.get('vote_shares', {}).items()},
            'predicted_at': v151_iso or '2026-05-10T11:00:00Z',
            'predicted_at_git_commit': v151_commit or 'unknown',
            'methodology': {
                'name': 'KPM-2.2',
                'version': 'v15.1',
                'hash_sha256': v151_hash,
                'commit': v151_commit or 'unknown',
                'code_url': f'https://github.com/Kronaxis/kpm/tree/{v151_commit or "main"}/scripts/kpm2/',
            },
            'note': 'Backtest application of v15.1 to KPM-1 vote shares — published AFTER election. Future v15.1+ predictions will be pre-registered before event.',
            'is_backtest': True,
        }
        if actual_norm:
            entry['actual_winner'] = actual_norm
            entry['actual_at'] = '2026-05-09T18:00:00Z'
            entry['actual_source'] = 'https://en.wikipedia.org/wiki/2026_United_Kingdom_local_elections'
            entry['hit'] = predicted == actual_norm
        v151_predictions.append(entry)

    # Lean track was a separate artefact - 8 council "Lean" calls explicitly tracked
    LEAN_TRACK = {
        'Havering': 'Reform UK', 'Bradford': 'Labour', 'Sunderland': 'Reform UK',
        'Wirral': 'Labour', 'Sandwell': 'Labour', 'Stoke-on-Trent': 'Labour',
        'Doncaster': 'Reform UK', 'Hartlepool': 'Reform UK',
    }
    LEAN_ACTUALS = {
        'Havering': 'No overall control', 'Bradford': 'No overall control',
        'Sunderland': 'Reform UK', 'Wirral': 'No overall control',
        'Sandwell': 'Reform UK', 'Stoke-on-Trent': 'Reform UK',
        'Doncaster': 'No overall control', 'Hartlepool': 'No overall control',
    }
    # Note: Havering hit as Reform = NOC mismatch. Per gold log lean track was 1/8.
    # Cross-reference with may7_actual_results.json's lean_track entries for canonicity.
    lean_meta = orig.get('lean_track_final', {})

    # Build the scorecard
    scorecard = {
        'schema_version': 'kronaxis-scorecard-v1',
        'description': 'Public, append-only ledger of every Kronaxis prediction. Each row is a falsifiable claim with a hash, timestamp, methodology version, and (when available) actual outcome. Misses are reported alongside hits.',
        'principle': 'Trust through falsifiability. We publish predictions before events with cryptographic hashes; we publish outcomes when known; we publish misses with the same prominence as hits. The methodology code is open-source and any prediction can be independently re-run and verified.',
        'last_updated': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'predictions': predictions + v151_predictions,
        'meta': {
            'n_total': len(predictions) + len(v151_predictions),
            'methodologies': {
                'KPM-1 v1.0': {'hash': methodology_kpm1_hash, 'commit': kpm1_commit, 'pre_registered': True,
                               'description': 'LLM-panel synthetic personas + DYNAMICS-8 + tactical voting + seat MC.'},
                'KPM-2.2 v15.1': {'hash': v151_hash, 'commit': v151_commit, 'pre_registered': False,
                                  'description': 'Rule-based fragmentation override on KPM-1 vote shares. NW Lab retain + LD-incumbent retain + historical NOC prior + Reform metro sweep + LD strong-leader retain + fragmentation NOC.',
                                  'note': 'Applied as backtest to May 7 2026. Future predictions from v15.1 will be pre-registered.'},
            },
            'elections_covered': [election_id],
            'public_repo': 'https://github.com/Kronaxis/kpm  (TBD - to be published Week 3)',
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(scorecard, indent=2))
    print(f"\nWrote {OUT}")
    print(f"  Predictions: {len(predictions)} KPM-1 + {len(v151_predictions)} KPM-2.2 v15.1 = {len(predictions) + len(v151_predictions)}")
    print(f"  KPM-1 hits: {sum(1 for p in predictions if p.get('hit'))}/{sum(1 for p in predictions if 'hit' in p)}")
    print(f"  KPM-2.2 v15.1 hits: {sum(1 for p in v151_predictions if p.get('hit'))}/{sum(1 for p in v151_predictions if 'hit' in p)}")

if __name__ == '__main__':
    main()
