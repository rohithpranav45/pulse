"""
One-time uploader — seed the private HF Dataset the Space pulls from.
====================================================================

The HF Space build bakes the parquet data lake from a private HF Dataset, and
``backend/hf_persist.py`` syncs the SQLite paper book to/from the same Dataset
at runtime. This script creates that Dataset and uploads:

    parquet/*.parquet   — the ~534 MB data lake (Data/parquet)
    db/pulse_cache.db   — the current paper book, as a seed (optional)

Run once from the repo root with a HF *write* token::

    python deploy/hf_space/upload_data.py --repo <username>/pulse-data --token hf_xxx
    #  or set HF_TOKEN in the environment and omit --token

Re-running is safe (idempotent create; files are overwritten). The big parquet
upload is bandwidth-bound — expect it to take a while on a home connection.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="dataset repo id, e.g. user/pulse-data")
    ap.add_argument("--token", default=os.environ.get("HF_TOKEN"), help="HF write token")
    ap.add_argument(
        "--skip-db", action="store_true", help="upload only the parquet lake, not the paper book"
    )
    args = ap.parse_args()

    if not args.token:
        sys.exit("error: need a write token via --token or the HF_TOKEN env var")

    from huggingface_hub import HfApi

    api = HfApi(token=args.token)

    print(f"- ensuring dataset {args.repo} exists (private)...")
    api.create_repo(args.repo, repo_type="dataset", private=True, exist_ok=True)

    parquet = _REPO_ROOT / "Data" / "parquet"
    if not parquet.is_dir():
        sys.exit(f"error: {parquet} not found - is the /Data lake present on this machine?")

    n = len(list(parquet.glob("*.parquet")))
    size_mb = sum(f.stat().st_size for f in parquet.rglob("*")) / 1_048_576
    print(f"- uploading {n} parquet files ({size_mb:.0f} MB) -> {args.repo}/parquet ...")
    api.upload_folder(
        folder_path=str(parquet),
        path_in_repo="parquet",
        repo_id=args.repo,
        repo_type="dataset",
        commit_message="upload parquet data lake",
    )

    if not args.skip_db:
        db = _REPO_ROOT / "backend" / "db" / "pulse_cache.db"
        if db.exists():
            print(f"- seeding paper book -> {args.repo}/db/pulse_cache.db ...")
            api.upload_file(
                path_or_fileobj=str(db),
                path_in_repo="db/pulse_cache.db",
                repo_id=args.repo,
                repo_type="dataset",
                commit_message="seed paper book",
            )
        else:
            print("- (no local paper book to seed - the Space will start a fresh one)")

    print(f"\n[done] Dataset ready: https://huggingface.co/datasets/{args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
