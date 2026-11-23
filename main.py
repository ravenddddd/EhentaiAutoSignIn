"""Command line entry point: run one check-in or start the Web UI and scheduler."""
import argparse
import logging
import threading
import time

import schedule

from ehentai import config, runner, web
from ehentai.config import scheduled_times
from ehentai.log_setup import LOG_FORMAT, configure_file_logging

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        """Route argument errors through the shared logging and exit handling."""
        raise ValueError(message)


def run_once(trigger='startup'):
    """Run one check-in and return True when it succeeded or was already done."""
    record = runner.run_once(trigger)
    return record is not None and record['result'] not in ('error', 'unconfigured')


def run_service():
    """Start the Web UI, then run a check-in now and at every scheduled time."""
    times = scheduled_times()
    password = config.setting('WEB_PASSWORD')
    if not password:
        raise ValueError('WEB_PASSWORD is required to start the Web UI.')
    port = config.web_port()

    server = web.serve(port, password)
    logging.info('Web UI listening on port %s', port)

    scheduler = schedule.Scheduler()
    for scheduled_time in times:
        scheduler.every().day.at(scheduled_time).do(runner.run_once, 'scheduled')

    logging.info('Scheduled check-ins (local time): %s', ', '.join(times))
    logging.info('Next run: %s', scheduler.next_run)
    logging.info('Running a check-in now.')
    threading.Thread(target=run_once, args=('startup',), name='startup-run', daemon=True).start()

    try:
        while True:
            scheduler.run_pending()
            time.sleep(1)
    finally:
        server.shutdown()


def main():
    parser = ArgumentParser(description='E-Hentai auto check-in')
    parser.add_argument('--once', action='store_true', help='run one check-in and exit')
    try:
        configure_file_logging()
        args = parser.parse_args()
        if args.once:
            return 0 if run_once('cli') else 1
        run_service()
    except KeyboardInterrupt:
        logging.info('Stopped.')
        return 0
    except Exception as exc:
        logging.error('Startup failed: %s: %s', type(exc).__name__, exc)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
