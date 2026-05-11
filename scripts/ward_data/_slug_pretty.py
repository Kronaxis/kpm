"""Shared slug → pretty council-name conversion.

Democracy Club uses lowercase-hyphen slugs (`newcastle-upon-tyne`,
`stoke-on-trent`, `kingston-upon-hull`). Our actuals data uses the
official council names which keep prepositions lowercase
(`Newcastle upon Tyne`, `Stoke-on-Trent` keeps hyphens).

This shared helper handles the special cases.
"""
from __future__ import annotations

LOWERCASE_WORDS = {'upon', 'on', 'of', 'and', 'the', 'le', 'la', 'in'}

# Direct overrides where simple rules don't work
OVERRIDES = {
    'kingston-upon-hull': 'Kingston upon Hull',
    'kingston-upon-thames': 'Kingston upon Thames',
    'newcastle-upon-tyne': 'Newcastle upon Tyne',
    'newcastle-under-lyme': 'Newcastle-under-Lyme',
    'stoke-on-trent': 'Stoke-on-Trent',
    'st-helens': 'St Helens',
    'st-albans': 'St Albans',
    'st-edmundsbury': 'St Edmundsbury',
    'isle-of-wight': 'Isle of Wight',
    'isles-of-scilly': 'Isles of Scilly',
    'wyre-forest': 'Wyre Forest',
    'tower-hamlets': 'Tower Hamlets',
    'redcar-and-cleveland': 'Redcar and Cleveland',
    'bath-and-north-east-somerset': 'Bath and North East Somerset',
    'kensington-and-chelsea': 'Kensington and Chelsea',
    'hammersmith-and-fulham': 'Hammersmith and Fulham',
    'barking-and-dagenham': 'Barking and Dagenham',
    'kingston-upon-thames': 'Kingston upon Thames',
}

def slug_to_pretty(slug: str) -> str:
    if slug in OVERRIDES:
        return OVERRIDES[slug]
    parts = slug.split('-')
    out = []
    for i, p in enumerate(parts):
        if i > 0 and p.lower() in LOWERCASE_WORDS:
            out.append(p.lower())
        else:
            out.append(p.capitalize())
    return ' '.join(out)

if __name__ == '__main__':
    tests = [
        ('newcastle-upon-tyne', 'Newcastle upon Tyne'),
        ('birmingham', 'Birmingham'),
        ('barking-and-dagenham', 'Barking and Dagenham'),
        ('stoke-on-trent', 'Stoke-on-Trent'),
        ('isle-of-wight', 'Isle of Wight'),
        ('hartlepool', 'Hartlepool'),
        ('newcastle-under-lyme', 'Newcastle-under-Lyme'),
    ]
    for slug, expected in tests:
        got = slug_to_pretty(slug)
        ok = '✓' if got == expected else '✗'
        print(f'  {ok}  {slug:30s} → {got:30s} (expected: {expected})')
