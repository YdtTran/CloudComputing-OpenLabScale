import argparse
import json

from .preflight import preflight


def main():
    parser = argparse.ArgumentParser(description='Measured workload experiment')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('preflight')
    replay = sub.add_parser('run')
    replay.add_argument('source')
    replay.add_argument('output')
    args = parser.parse_args()
    if args.command == 'run':
        from .run import run
        try:
            print(run(args.source, args.output))
        except (ValueError, RuntimeError, OSError, KeyboardInterrupt) as error:
            parser.exit(2, f'error: {error}\n')
        return 0
    evidence = preflight()
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['status'] == 'attached' else 1


if __name__ == '__main__':
    raise SystemExit(main())
