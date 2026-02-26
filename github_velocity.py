#!/usr/bin/env python3
"""
Velocity-style metrics from GitHub API: Releases and PR Merges.

Replicates metrics like Dev 360 Velocity:
- RELEASES: R30D (releases in last 30 days), current month count, projection
- PR MERGES: R30D (merged PRs in last 30 days), current month count, projection

Usage:
  export GITHUB_TOKEN=ghp_xxx   # optional; increases rate limit
  python github_velocity.py --owner OWNER --repo REPO [--author LOGIN]
  python github_velocity.py --owner OWNER --repo REPO --author sanjayrane  # filter PRs by author

Output: JSON summary + optional text report. Use the JSON for building dashboards.
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

GITHUB_API = "https://api.github.com"


def _headers(token: str | None) -> dict[str, str]:
    h = {"Accept": "application/vnd.github.v3+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get_all_pages(
    url: str,
    token: str | None,
    params: dict[str, Any] | None = None,
) -> list[dict]:
    params = params or {}
    params.setdefault("per_page", 100)
    out: list[dict] = []
    while url:
        r = requests.get(url, headers=_headers(token), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            out.extend(data)
        else:
            out.append(data)
        url = r.links.get("next", {}).get("url") if "next" in r.links else None
        params = None
    return out


def fetch_releases(owner: str, repo: str, token: str | None) -> list[dict]:
    """Fetch all releases (published); each has published_at."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases"
    return _get_all_pages(url, token)


def fetch_merged_pulls(
    owner: str,
    repo: str,
    token: str | None,
    author: str | None = None,
) -> list[dict]:
    """Fetch closed PRs and keep only merged (merged_at is set)."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
    all_closed: list[dict] = []
    params: dict[str, Any] = {"state": "closed", "per_page": 100}
    page = 1
    while True:
        r = requests.get(
            url,
            headers=_headers(token),
            params={**params, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        all_closed.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    merged = [p for p in all_closed if p.get("merged_at")]
    if author:
        author_lower = author.lower()
        merged = [p for p in merged if (p.get("user") or {}).get("login", "").lower() == author_lower]
    return merged


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def in_last_n_days(dt: datetime | None, n: int, now: datetime) -> bool:
    if not dt:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days <= n


def in_month(dt: datetime | None, year: int, month: int) -> bool:
    if not dt:
        return False
    return dt.year == year and dt.month == month


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime(year, month + 1, 1) - timedelta(days=1)).day


def compute_velocity(
    events: list[dict],
    date_key: str,
    target_per_month: float = 0.0,
) -> dict:
    """Compute R30D, current month count, and projection."""
    now = datetime.now(timezone.utc)
    today = now.date()
    days_in_month = _days_in_month(today.year, today.month)
    days_elapsed = today.day

    r30d = sum(
        1
        for e in events
        if in_last_n_days(parse_iso(e.get(date_key)), 30, now)
    )
    current_month = [
        e
        for e in events
        if in_month(parse_iso(e.get(date_key)), today.year, today.month)
    ]
    current_count = len(current_month)
    if days_elapsed > 0:
        projection = (current_count / days_elapsed) * days_in_month
    else:
        projection = 0.0

    return {
        "r30d": r30d,
        "current_month_count": current_count,
        "current_month_projection": round(projection, 2),
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "target_per_month": target_per_month,
        "projection_vs_target_pct": (
            round((projection - target_per_month) / target_per_month * 100, 0)
            if target_per_month
            else None
        ),
    }


def cumulative_by_day(events: list[dict], date_key: str, year: int, month: int) -> list[dict]:
    """Daily cumulative counts for the given month (for cumulative line graph)."""
    month_events = [
        e
        for e in events
        if in_month(parse_iso(e.get(date_key)), year, month)
    ]
    by_day: dict[int, int] = {}
    for e in month_events:
        dt = parse_iso(e.get(date_key))
        if dt:
            by_day[dt.day] = by_day.get(dt.day, 0) + 1
    cumul = 0
    result = []
    for d in range(1, 32):
        cumul += by_day.get(d, 0)
        result.append({"day": d, "cumulative": cumul})
    return result


def monthly_history(events: list[dict], date_key: str, num_months: int = 12) -> list[dict]:
    """Monthly counts for history graph (last num_months including current)."""
    now = datetime.now(timezone.utc)
    out = []
    y, m = now.year, now.month
    for _ in range(num_months):
        count = sum(
            1
            for e in events
            if in_month(parse_iso(e.get(date_key)), y, m)
        )
        out.append({"year": y, "month": m, "count": count})
        m -= 1
        if m < 1:
            m, y = 12, y - 1
    out.reverse()
    return out


def run(
    owner: str,
    repo: str,
    token: str | None = None,
    author: str | None = None,
    release_target: float = 2.0,
    pr_target: float = 3.0,
) -> dict:
    token = token or os.environ.get("GITHUB_TOKEN")
    releases = fetch_releases(owner, repo, token)
    pulls = fetch_merged_pulls(owner, repo, token, author=author)

    now = datetime.now(timezone.utc)
    today = now.date()

    release_velocity = compute_velocity(
        releases,
        "published_at",
        target_per_month=release_target,
    )
    pr_velocity = compute_velocity(
        pulls,
        "merged_at",
        target_per_month=pr_target,
    )

    release_velocity["cumulative_current_month"] = cumulative_by_day(
        releases, "published_at", today.year, today.month
    )
    release_velocity["monthly_history"] = monthly_history(releases, "published_at")

    pr_velocity["cumulative_current_month"] = cumulative_by_day(
        pulls, "merged_at", today.year, today.month
    )
    pr_velocity["monthly_history"] = monthly_history(pulls, "merged_at")

    return {
        "repo": f"{owner}/{repo}",
        "author_filter": author,
        "as_of": now.isoformat(),
        "releases": release_velocity,
        "pr_merges": pr_velocity,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="GitHub Velocity: releases and PR merges metrics via API"
    )
    ap.add_argument("--owner", required=True, help="Repo owner (org or user)")
    ap.add_argument("--repo", required=True, help="Repo name")
    ap.add_argument("--author", default=None, help="Filter PR merges by GitHub login (e.g. sanjayrane)")
    ap.add_argument("--release-target", type=float, default=2.0, help="Target releases per month")
    ap.add_argument("--pr-target", type=float, default=3.0, help="Target PR merges per month")
    ap.add_argument("--json", action="store_true", help="Print only JSON")
    args = ap.parse_args()

    result = run(
        owner=args.owner,
        repo=args.repo,
        author=args.author,
        release_target=args.release_target,
        pr_target=args.pr_target,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return

    # Text report (like a minimal dashboard summary)
    r = result["releases"]
    p = result["pr_merges"]
    print(f"\nVelocity for {result['repo']}" + (f" (PR author: {result['author_filter']})" if result["author_filter"] else ""))
    print("=" * 60)
    print("RELEASES")
    print(f"  Target: {r['target_per_month']}  |  R30D: {r['r30d']}  |  Current month: {r['current_month_count']}  |  Projection: {r['current_month_projection']}", end="")
    if r.get("projection_vs_target_pct") is not None:
        print(f"  ({r['projection_vs_target_pct']:+.0f}% vs target)")
    else:
        print()
    print("\nPR MERGES")
    print(f"  Target: {p['target_per_month']}  |  R30D: {p['r30d']}  |  Current month: {p['current_month_count']}  |  Projection: {p['current_month_projection']}", end="")
    if p.get("projection_vs_target_pct") is not None:
        print(f"  ({p['projection_vs_target_pct']:+.0f}% vs target)")
    else:
        print()
    print("\n(Full JSON for charts: run with --json)")


if __name__ == "__main__":
    main()
