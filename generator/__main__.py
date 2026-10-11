"""uv run python -m generator --seed 42 --scale 1.0 --out data/"""
import argparse
import json
import time
from datetime import date
from pathlib import Path

from .config import Config
from .emit import Emitter
from .output import write_raw, write_truth
from .sim import Sim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 14))
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--no-traps", action="store_true")
    a = ap.parse_args()
    cfg = Config(seed=a.seed, scale=a.scale, end=a.end, traps_enabled=not a.no_traps)
    t0 = time.time()
    sim = Sim(cfg)
    sim.build()
    print(f"entities: {len(sim.orgs):,} orgs, {len(sim.accounts):,} accounts, {len(sim.opps):,} opps "
          f"({time.time()-t0:.0f}s)")
    em = Emitter(sim, a.out)
    em.run()
    print(f"activity emitted ({time.time()-t0:.0f}s)")
    counts = write_raw(sim, em, a.out)
    counts.update({f"truth.{k}": v for k, v in write_truth(sim, em, a.out).items()})
    (a.out / "manifest.json").write_text(json.dumps(
        dict(seed=cfg.seed, scale=cfg.scale, end=str(cfg.end), traps=cfg.traps_enabled, rows=counts), indent=2))
    for k, v in counts.items():
        print(f"  {k:40s} {v:>12,}")
    print(f"done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
