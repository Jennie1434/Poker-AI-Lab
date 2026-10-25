"""Configurable self-play CFR training with checkpoints and convergence logs.

Training outputs (checkpoints, curves) live in a private folder and never use
benchmark seeds. Evaluation loads a frozen checkpoint and performs no updates.
"""
import argparse
import csv
import json
from pathlib import Path
import time

from .cfr import CFRTrainer, VARIANTS, exploitability
from .toy_games import GAMES


def train_toy(game_name: str, variant: str, iterations: int, output: Path, seed: int = 0,
              every: int = 0, resume: Path | None = None) -> dict:
    """Train on Kuhn/Leduc; log exact exploitability every ``every`` iterations."""
    game = GAMES[game_name]()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    trainer = CFRTrainer.load(game, resume) if resume else CFRTrainer(game, variant, seed)
    if resume and trainer.variant != variant:
        raise ValueError("Resumed checkpoint uses a different variant")
    curve = []
    started = time.process_time()

    def record(t):
        metrics = exploitability(game, t.average_strategy())
        curve.append({"iteration": t.iterations, "cpu_seconds": time.process_time() - started,
                      "information_sets": len(t.actions), **metrics})

    trainer.train(iterations, record, every)
    if not curve or curve[-1]["iteration"] != trainer.iterations:
        record(trainer)
    with (output / "convergence.csv").open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(curve[0]))
        writer.writeheader()
        writer.writerows(curve)
    trainer.save(output / "checkpoint.json", {"kind": "toy", "resumed_from": str(resume) if resume else None})
    summary = {"game": game_name, "variant": variant, "seed": trainer.seed,
               "iterations": trainer.iterations, "final": curve[-1]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    toy = sub.add_parser("toy", help="Kuhn or Leduc with exact exploitability")
    toy.add_argument("--game", choices=sorted(GAMES), required=True)
    toy.add_argument("--variant", choices=VARIANTS, default="plus")
    toy.add_argument("--iterations", type=int, required=True)
    toy.add_argument("--seed", type=int, default=0)
    toy.add_argument("--every", type=int, default=0, help="log exploitability every N iterations")
    toy.add_argument("--resume", type=Path)
    toy.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "toy":
        result = train_toy(args.game, args.variant, args.iterations, args.output, args.seed, args.every, args.resume)
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
