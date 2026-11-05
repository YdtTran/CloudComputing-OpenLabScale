"""CLI entrypoint for running OpenLab-Scale Dashboard."""
import argparse
import sys
from dashboard.server import run_server


def main():
    parser = argparse.ArgumentParser(description="OpenLab-Scale Monitoring & License Management Dashboard")
    parser.add_argument("--port", type=int, default=8500, help="Port to listen on (default: 8500)")
    args = parser.parse_args()
    run_server(port=args.port)


if __name__ == "__main__":
    main()
