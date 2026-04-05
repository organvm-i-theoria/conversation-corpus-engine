# Fix: Spotlight (`mds_stores`) runaway — exclude Workspace from indexing

## Context

`mds_stores` (Spotlight indexer) has been at 87% CPU for **20 hours** (19:44 CPU time, running since
March 31). The cause: zero Spotlight exclusions + a 128-repo workspace with 2.1 GB of CCE state JSON,
plus the 8-hour CCE refresh writing ~28 MB of log and hundreds of corpus files. Spotlight is stuck in
a reindex loop trying to keep up with file churn it has no business indexing.

5,168 files changed in the last 24 hours in `~/Workspace` alone. None of these need Spotlight search —
the user uses ripgrep, Glob, and Grep for code search.

## Plan

### 1. Exclude heavy directories from Spotlight

Add these directories to Spotlight's exclusion list (System Settings > Spotlight > Privacy):

```bash
# Workspace — code search is done via ripgrep, not Spotlight
sudo mdutil -i off /Users/4jp/Workspace

# Docker VM disk — machine-generated
sudo mdutil -i off /Users/4jp/Library/Containers

# Homebrew — binary packages
sudo mdutil -i off /opt/homebrew
```

The `mdutil -i off` approach disables indexing per-path. For user-level directories within the boot
volume, we use the Privacy list API instead:

```bash
# Add to Spotlight Privacy exclusion list
defaults write com.apple.Spotlight orderedItems -array-add \
  '{"enabled"=true;"name"="EXCLUSION";"path"="/Users/4jp/Workspace";}'
```

However, the most reliable method on macOS Tahoe is through System Settings or the `mdutil` command.

### 2. Rebuild the corrupted Spotlight index

After adding exclusions, rebuild the index to clear the stuck state:

```bash
sudo mdutil -E /
```

This erases the current index and triggers a fresh rebuild that respects the new exclusions.

### 3. Verify

```bash
# Confirm Workspace indexing is off
mdutil -s /Users/4jp/Workspace

# Watch mds_stores CPU drop
ps -p 826 -o pid,pcpu,cputime
```

## Why not kill it?

Killing `mds_stores` (PID 826) would just restart it — launchd owns it. The fix is to reduce its
workload by excluding directories that generate churn but provide no Spotlight search value.
