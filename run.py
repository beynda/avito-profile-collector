#!/usr/bin/env python3
"""Collect public Avito profiles and export CSV/XLSX."""
from __future__ import annotations

import argparse
import sys
import signal
import yaml
import os
from pathlib import Path

from src.browser import launch_browser
from src.config import load_config
from src.db import open_db
from src.export import export
from src.logger import setup_logger
from src.scraper import run_scrape
from src import control
from src.session import prepare_session


def main(argv=None):
    parser = argparse.ArgumentParser(description="Avito public profile collector")
    parser.add_argument("--config", default="config.yaml", help="Configuration file path")
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Export existing database without collection",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser without a visible window",
    )
    parser.add_argument("--collect", action="store_true", help="Explicitly enable network collection")
    parser.add_argument('--session-ready', action='store_true', help='Explicitly confirm browser preparation for unattended collection')
    parser.add_argument('--prepare-session', action='store_true', help='Pause for optional manual login before collection')
    args = parser.parse_args(argv)
    if args.collect and args.export_only:
        parser.error('Choose either --collect or --export-only.')
    if not args.collect and not args.export_only:
        parser.print_help()
        return 0

    try:
        cfg = load_config(args.config)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.error(f'Invalid configuration: {error}')
    logger = setup_logger(cfg.resolve("data"))

    db_path = cfg.resolve(cfg.db_path)
    excel_path = cfg.resolve(cfg.output.excel_path)
    csv_path = cfg.resolve(cfg.output.csv_path)

    with open_db(db_path) as db:
        if args.export_only:
            export(db, excel_path, csv_path, logger)
            return

        headless = cfg.browser.headless or args.headless
        user_data_dir = cfg.resolve(cfg.browser.user_data_dir)

        logger.info(
            f"Starting collection. Queries: {len(cfg.keywords)}, "
            f"regions: {len(cfg.regions)}, headless={headless}."
        )
        logger.info(
            f"Existing database: {db.count_profiles()} unique profiles."
        )

        playwright, context = launch_browser(
            user_data_dir=user_data_dir, headless=headless, proxy=cfg.proxy
        )
        stats = None
        interrupted = False
        failed = False
        control.requested = False
        previous_handler = signal.signal(signal.SIGINT, control.request_stop)
        try:
            logger.info('Login is optional. This browser uses its own local profile; use --prepare-session if you want to sign in manually.')
            if not args.prepare_session or prepare_session(context, logger, headless, args.session_ready):
                stats = run_scrape(context, cfg, db, logger)
            else:
                failed = True
        except KeyboardInterrupt:
            interrupted = True
            logger.warning("Interrupted. Saved data remains in SQLite. Processed listings are skipped on restart.")
        except Exception:
            failed = True
            logger.exception('Collection failed. Saved profiles will still be exported.')
        finally:
            # Export committed records before browser shutdown, which can stall
            # after interruption inside a Playwright operation.
            try:
                export(db, excel_path, csv_path, logger)
            finally:
                logger.info('Closing browser. Please wait for shutdown to complete.')
                for resource, method in ((context, "close"), (playwright, "stop")):
                    try:
                        getattr(resource, method)()
                    except (Exception, KeyboardInterrupt) as error:
                        logger.warning("Browser cleanup failed: %s", error)
                signal.signal(signal.SIGINT, previous_handler)
        if interrupted:
            return 130
        return 1 if failed or (stats is not None and stats.errors) else 0


if __name__ == "__main__":
    if '--collect' in sys.argv and not os.environ.get('PROFILE_COLLECTOR_STOP_FILE'):
        from src.supervisor import supervise
        sys.exit(supervise([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]))
    sys.exit(main())
