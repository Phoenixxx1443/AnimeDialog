import argparse
import sys

from .pipeline import process_job


def main():
    from .processes import bind_worker_children

    bind_worker_children()
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    return process_job(args.project, args.job)


if __name__ == "__main__":
    sys.exit(main())
