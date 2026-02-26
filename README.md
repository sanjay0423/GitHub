# GitHub Velocity

Python script to compute **Velocity-style metrics** (like Dev 360) using the GitHub API: **Releases** and **PR Merges**.

## Is there an OOB report from GitHub?

No. GitHub does not provide an out-of-the-box "Velocity" report with targets, R30D, and projections. You get:

- **GitHub Insights** (Enterprise): high-level usage, not release/PR velocity.
- **Issue Metrics Action**: time-to-close, etc., not cumulative/monthly velocity.
- **Activity dashboard** (Enterprise Server): org-level activity, not per-user velocity with targets.

So this script uses the **GitHub REST API** to fetch data and compute the metrics yourself.

## Metrics produced

| Metric | Meaning |
|--------|--------|
| **R30D** | Count in the last 30 days (releases or merged PRs) |
| **Current month** | Count so far in the current calendar month |
| **Projection** | Projected total for the month: `(current_count / days_elapsed) * days_in_month` |
| **Cumulative by day** | Daily cumulative counts for the current month (for a cumulative line chart) |
| **Monthly history** | Count per month for the last 12 months (for a trend chart) |

## Setup

```bash
cd ~/code/GitHub
pip install -r requirements.txt
```

Optional: set a **GitHub token** for higher rate limits and private repos:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

Create a token: GitHub → Settings → Developer settings → Personal access tokens (classic). Scopes: `repo` (for private repos) or no scope for public-only.

## Usage

**One repo, all releases and all merged PRs:**

```bash
python github_velocity.py --owner apache --repo spark
```

**Filter PR merges by author (e.g. "Sanjay Rane" → use GitHub username):**

```bash
python github_velocity.py --owner myorg --repo myrepo --author sanjayrane
```

**Custom targets and JSON only:**

```bash
python github_velocity.py --owner myorg --repo myrepo --release-target 2 --pr-target 3 --json
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `--owner` | Repo owner (org or user) |
| `--repo` | Repo name |
| `--author` | Filter PR merges by GitHub login |
| `--release-target` | Target releases per month (default 2.0) |
| `--pr-target` | Target PR merges per month (default 3.0) |
| `--json` | Print only JSON (for dashboards) |

## Output

- **Without `--json`**: Short text summary (target, R30D, current month, projection, % vs target).
- **With `--json`**: Full JSON with `releases` and `pr_merges` (including `cumulative_current_month` and `monthly_history`) for building your own dashboard (e.g. charts like in the Dev 360 screenshot).

## Example (text report)

```
Velocity for apache/spark
============================================================
RELEASES
  Target: 2.0  |  R30D: 1  |  Current month: 0  |  Projection: 0.0  (-100% vs target)

PR MERGES
  Target: 3.0  |  R30D: 42  |  Current month: 15  |  Projection: 32.5  (+983% vs target)

(Full JSON for charts: run with --json)
```

## APIs used

- **Releases:** `GET /repos/{owner}/{repo}/releases` (uses `published_at`)
- **Merged PRs:** `GET /repos/{owner}/{repo}/pulls?state=closed`, then filter by `merged_at` (and optionally `user.login` for `--author`)
