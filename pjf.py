"""PJF v2: remote video game jobs, open to Spain. Python 3.9+, standard library only.

Usage:
  python pjf.py            run the collectors, rebuild the page, then open it with marks enabled
  python pjf.py run        run only (this is what GitHub Actions does)
  python pjf.py serve      open the current page with marks enabled, no run
  python pjf.py page       rebuild docs/index.html from saved state, no network

Options for run:
  --probe N    new companies to probe for an ATS board this run (default 40)
  --no-ats     skip company job boards
  --no-feeds   skip RSS/Atom feeds
  --no-remote  skip general remote boards (Remotive, WWR, ...)
  --no-workday skip Workday career sites
"""
import argparse
import sys

from pjf import pipeline, server


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # Windows consoles and odd characters
        except AttributeError:
            pass

    ap = argparse.ArgumentParser(description="PJF v2")
    ap.add_argument("cmd", nargs="?", default="all", choices=["all", "run", "serve", "page"])
    ap.add_argument("--probe", type=int, default=40)
    ap.add_argument("--no-ats", action="store_true")
    ap.add_argument("--no-feeds", action="store_true")
    ap.add_argument("--no-remote", action="store_true")
    ap.add_argument("--no-workday", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd in ("all", "run"):
        pipeline.run(probe=args.probe, use_ats=not args.no_ats, use_feeds=not args.no_feeds,
                     use_remote=not args.no_remote, use_workday=not args.no_workday)
        if args.cmd == "run":
            print("To open the page with mark buttons: python pjf.py serve")
    if args.cmd == "page":
        pipeline.rebuild_page()
    if args.cmd in ("all", "serve"):
        server.serve(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
