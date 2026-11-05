"""Pre-loads the cache for known niches, so most searches are instant and cost no rate limit.
Run: python -m app.prewarm [max_brands_per_niche]   Safe to stop and rerun: finished lookups come from the cache."""
import json
import sys

from . import config, niche as niches, service
from .crustdata import Unavailable


def main(per_niche: int = 15) -> None:
    for i, n in enumerate(json.loads((config.DATA / 'known_niches.json').read_text(encoding='utf8')), 1):
        try:
            service.seed_brands(n)
            todo = service.candidates_for(n)[:per_niche]
            service.assess(todo, n)
            print(f'[{i}] {n}: {len(todo)} brands, learned {niches.profile(n)["learned"][:5]}', flush=True)
        except Unavailable as e:
            print(f'[{i}] {n}: skipped ({e})', flush=True)


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 15)
