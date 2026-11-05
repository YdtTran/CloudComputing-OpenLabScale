"""Run with python3 -m simulation."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Offline synthetic session generation, validation and recommendation evaluation.')
    sub = parser.add_subparsers(dest='command', required=True)
    g = sub.add_parser('generate', help='Generate a deterministic synthetic bundle')
    g.add_argument('output', type=Path)
    g.add_argument('--seed', type=int, default=42)
    g.add_argument('--count', type=int, default=10)
    g.add_argument('--start-offset-ms', type=int, default=0)
    g.add_argument('--cpu-limit-cores', type=float, default=.5)
    g.add_argument('--memory-limit-mb', type=int, default=256)
    g.add_argument('--overwrite', action='store_true')
    v = sub.add_parser('validate', help='Validate a versioned bundle')
    v.add_argument('bundle', type=Path)
    for command in ['predict', 'score', 'evaluate']:
        p = sub.add_parser(command, help={'predict': 'Export causal predictions without reading truth', 'score': 'Score finalized predictions', 'evaluate': 'Predict, then score offline'}[command])
        p.add_argument('bundle', type=Path)
        p.add_argument('output', type=Path)
        if command != 'score':
            p.add_argument('--policy-config', type=Path, help='JSON overrides of policy thresholds')
    args = parser.parse_args()
    try:
        if args.command == 'generate':
            from .generator import generate
            generate(args.output, args.seed, args.count, args.start_offset_ms, args.cpu_limit_cores, args.memory_limit_mb, args.overwrite)
        elif args.command == 'validate':
            from .validation import validate
            validate(args.bundle)
            print('Bundle valid')
        else:
            if args.command in ('predict', 'evaluate'):
                from .policies import predict
                config = json.loads(args.policy_config.read_text()) if args.policy_config else None
                predict(args.bundle, args.output, config)
            if args.command in ('score', 'evaluate'):
                from .scoring import score
                score(args.bundle, args.output)
    except (ValueError, OSError, KeyError, TypeError) as e:
        parser.exit(2, f'error: {e}\n')


if __name__ == '__main__':
    main()
