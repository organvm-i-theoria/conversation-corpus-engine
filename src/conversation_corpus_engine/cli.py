from __future__ import annotations

import argparse
import json
from pathlib import Path

from .corpus_candidates import (
    corpus_candidate_history_path,
    load_corpus_candidate_manifest,
    promote_corpus_candidate,
    review_corpus_candidate,
    rollback_corpus_promotion,
    stage_corpus_candidate,
)
from .evaluation import run_corpus_evaluation
from .evaluation_bootstrap import bootstrap_provider_evaluation
from .federated_canon import (
    load_federated_review_history,
    load_federated_review_queue,
    resolve_federated_review_item,
)
from .federation import build_federation, list_registered_corpora, upsert_corpus
from .governance_candidates import (
    apply_policy_candidate,
    review_policy_candidate,
    rollback_policy_application,
    stage_policy_candidate,
)
from .governance_policy import load_or_create_promotion_policy
from .governance_replay import build_policy_replay_payload, write_policy_replay_artifacts
from .migration import seed_registry_from_staging
from .paths import default_project_root
from .provider_catalog import default_source_drop_root
from .provider_discovery import discover_provider_uploads, render_provider_discovery_text
from .provider_import import import_provider_corpus
from .provider_readiness import (
    build_provider_readiness,
    render_provider_readiness_text,
    write_provider_readiness_reports,
)
from .provider_refresh import refresh_provider_corpus
from .schema_validation import (
    SCHEMA_CATALOG,
    list_schemas,
    load_schema,
    schema_path,
    validate_json_file,
)
from .source_lifecycle import compute_source_freshness
from .source_policy import load_source_policy, set_source_policy, source_policy_history_path
from .surface_exports import (
    build_mcp_context_payload,
    build_surface_manifest,
    export_surface_bundle,
    write_mcp_context_artifacts,
    write_surface_manifest_artifacts,
)


def parse_threshold_overrides(values: list[str] | None) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for item in values or []:
        key, sep, raw_value = item.partition("=")
        if not sep or not key.strip() or not raw_value.strip():
            raise ValueError(f"Threshold override must be KEY=VALUE, got: {item}")
        overrides[key.strip()] = float(raw_value.strip())
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Conversation corpus engine")
    subparsers = parser.add_subparsers(dest="group", required=True)

    corpus = subparsers.add_parser("corpus", help="Manage registered corpora")
    corpus_sub = corpus.add_subparsers(dest="action", required=True)

    corpus_list = corpus_sub.add_parser("list", help="List registered corpora")
    corpus_list.add_argument("--project-root", type=Path, default=default_project_root())
    corpus_list.add_argument("--json", action="store_true")

    corpus_register = corpus_sub.add_parser("register", help="Register a corpus root")
    corpus_register.add_argument("corpus_root", type=Path)
    corpus_register.add_argument("--project-root", type=Path, default=default_project_root())
    corpus_register.add_argument("--corpus-id")
    corpus_register.add_argument("--name")
    corpus_register.add_argument("--default", action="store_true")

    federation = subparsers.add_parser("federation", help="Build federated outputs")
    federation_sub = federation.add_subparsers(dest="action", required=True)
    federation_build = federation_sub.add_parser("build", help="Build federation artifacts")
    federation_build.add_argument("--project-root", type=Path, default=default_project_root())

    migration = subparsers.add_parser("migration", help="Migration helpers")
    migration_sub = migration.add_subparsers(dest="action", required=True)
    migration_seed = migration_sub.add_parser(
        "seed-from-staging", help="Register corpora from a staging root"
    )
    migration_seed.add_argument("staging_root", type=Path)
    migration_seed.add_argument("--project-root", type=Path, default=default_project_root())
    migration_seed.add_argument("--prefer-default", default="chatgpt-history")

    provider = subparsers.add_parser("provider", help="Inspect provider intake and readiness")
    provider_sub = provider.add_subparsers(dest="action", required=True)
    provider_discover = provider_sub.add_parser(
        "discover", help="Inspect provider source-drop inboxes"
    )
    provider_discover.add_argument("--project-root", type=Path, default=default_project_root())
    provider_discover.add_argument("--source-drop-root", type=Path)
    provider_discover.add_argument("--json", action="store_true")
    provider_readiness = provider_sub.add_parser(
        "readiness", help="Build provider readiness summary"
    )
    provider_readiness.add_argument("--project-root", type=Path, default=default_project_root())
    provider_readiness.add_argument("--source-drop-root", type=Path)
    provider_readiness.add_argument("--json", action="store_true")
    provider_readiness.add_argument("--write", action="store_true")
    provider_import = provider_sub.add_parser(
        "import", help="Import a provider source into a corpus"
    )
    provider_import.add_argument("--project-root", type=Path, default=default_project_root())
    provider_import.add_argument(
        "--provider", choices=["claude", "gemini", "grok", "perplexity", "copilot"], required=True
    )
    provider_import.add_argument("--mode", choices=["upload", "local-session"], default="upload")
    provider_import.add_argument("--source-drop-root", type=Path)
    provider_import.add_argument("--source-path", type=Path)
    provider_import.add_argument("--local-root", type=Path)
    provider_import.add_argument("--output-root", type=Path)
    provider_import.add_argument("--corpus-id")
    provider_import.add_argument("--name")
    provider_import.add_argument("--register", action="store_true")
    provider_import.add_argument("--build", action="store_true")
    provider_import.add_argument("--no-bootstrap-eval", action="store_true")
    provider_import.add_argument("--json", action="store_true")
    provider_bootstrap = provider_sub.add_parser(
        "bootstrap-eval", help="Scaffold manual evaluation files for a provider corpus"
    )
    provider_bootstrap.add_argument(
        "--provider", choices=["claude", "gemini", "grok", "perplexity", "copilot"], required=True
    )
    provider_bootstrap.add_argument("--project-root", type=Path, default=default_project_root())
    provider_bootstrap.add_argument("--target-root", type=Path)
    provider_bootstrap.add_argument("--policy-path", type=Path)
    provider_bootstrap.add_argument("--full-eval", action="store_true")
    provider_bootstrap.add_argument("--json", action="store_true")
    provider_refresh = provider_sub.add_parser(
        "refresh", help="Import, evaluate, and stage a refreshed provider corpus"
    )
    provider_refresh.add_argument(
        "--provider", choices=["claude", "gemini", "grok", "perplexity", "copilot"], required=True
    )
    provider_refresh.add_argument("--project-root", type=Path, default=default_project_root())
    provider_refresh.add_argument("--mode", choices=["upload", "local-session"])
    provider_refresh.add_argument("--source-drop-root", type=Path)
    provider_refresh.add_argument("--source-path", type=Path)
    provider_refresh.add_argument("--local-root", type=Path)
    provider_refresh.add_argument("--live-corpus-id")
    provider_refresh.add_argument("--candidate-root", type=Path)
    provider_refresh.add_argument("--no-bootstrap-eval", action="store_true")
    provider_refresh.add_argument("--no-eval", action="store_true")
    provider_refresh.add_argument("--approve", action="store_true")
    provider_refresh.add_argument("--promote", action="store_true")
    provider_refresh.add_argument("--note", default="")
    provider_refresh.add_argument("--json", action="store_true")

    schema = subparsers.add_parser("schema", help="Inspect and validate published artifact schemas")
    schema_sub = schema.add_subparsers(dest="action", required=True)
    schema_list = schema_sub.add_parser("list", help="List published schema contracts")
    schema_list.add_argument("--json", action="store_true")
    schema_show = schema_sub.add_parser("show", help="Show a schema contract")
    schema_show.add_argument("schema_name", choices=sorted(SCHEMA_CATALOG))
    schema_show.add_argument("--json", action="store_true")
    schema_validate = schema_sub.add_parser(
        "validate", help="Validate a JSON artifact against a schema"
    )
    schema_validate.add_argument("schema_name", choices=sorted(SCHEMA_CATALOG))
    schema_validate.add_argument("--path", type=Path, required=True)
    schema_validate.add_argument("--json", action="store_true")

    surface = subparsers.add_parser("surface", help="Export Meta/MCP-facing surface artifacts")
    surface_sub = surface.add_subparsers(dest="action", required=True)
    surface_manifest = surface_sub.add_parser(
        "manifest", help="Write the engine-facing surface manifest"
    )
    surface_manifest.add_argument("--project-root", type=Path, default=default_project_root())
    surface_manifest.add_argument("--source-drop-root", type=Path)
    surface_context = surface_sub.add_parser("context", help="Write the MCP-facing context payload")
    surface_context.add_argument("--project-root", type=Path, default=default_project_root())
    surface_context.add_argument("--source-drop-root", type=Path)
    surface_bundle = surface_sub.add_parser(
        "bundle", help="Write both exported surfaces and validation bundle"
    )
    surface_bundle.add_argument("--project-root", type=Path, default=default_project_root())
    surface_bundle.add_argument("--source-drop-root", type=Path)

    source_policy = subparsers.add_parser(
        "source-policy", help="Manage provider source authority policies"
    )
    source_policy_sub = source_policy.add_subparsers(dest="action", required=True)
    source_policy_show = source_policy_sub.add_parser("show", help="Show a provider source policy")
    source_policy_show.add_argument("--project-root", type=Path, default=default_project_root())
    source_policy_show.add_argument(
        "--provider", choices=["claude", "gemini", "grok", "perplexity", "copilot"], required=True
    )
    source_policy_show.add_argument("--json", action="store_true")
    source_policy_set = source_policy_sub.add_parser("set", help="Set a provider source policy")
    source_policy_set.add_argument("--project-root", type=Path, default=default_project_root())
    source_policy_set.add_argument(
        "--provider", choices=["claude", "gemini", "grok", "perplexity", "copilot"], required=True
    )
    source_policy_set.add_argument("--primary-root", type=Path, required=True)
    source_policy_set.add_argument("--primary-corpus-id", required=True)
    source_policy_set.add_argument("--fallback-root", type=Path)
    source_policy_set.add_argument("--fallback-corpus-id")
    source_policy_set.add_argument("--decision", default="manual")
    source_policy_set.add_argument("--note", default="")
    source_policy_set.add_argument("--json", action="store_true")
    source_policy_history = source_policy_sub.add_parser(
        "history", help="Show source policy history"
    )
    source_policy_history.add_argument("--project-root", type=Path, default=default_project_root())
    source_policy_history.add_argument("--json", action="store_true")

    policy = subparsers.add_parser("policy", help="Replay and govern promotion policy")
    policy_sub = policy.add_subparsers(dest="action", required=True)
    policy_show = policy_sub.add_parser("show", help="Show the live promotion policy")
    policy_show.add_argument("--project-root", type=Path, default=default_project_root())
    policy_show.add_argument("--json", action="store_true")
    policy_replay = policy_sub.add_parser(
        "replay", help="Replay the live or overridden policy against active corpora"
    )
    policy_replay.add_argument("--project-root", type=Path, default=default_project_root())
    policy_replay.add_argument("--set-threshold", action="append", default=[])
    policy_replay.add_argument("--write", action="store_true")
    policy_replay.add_argument("--json", action="store_true")
    policy_stage = policy_sub.add_parser("stage", help="Stage a policy candidate")
    policy_stage.add_argument("--project-root", type=Path, default=default_project_root())
    policy_stage.add_argument("--set-threshold", action="append", required=True)
    policy_stage.add_argument("--note", default="")
    policy_stage.add_argument("--json", action="store_true")
    policy_review = policy_sub.add_parser("review", help="Review a staged policy candidate")
    policy_review.add_argument("--project-root", type=Path, default=default_project_root())
    policy_review.add_argument("--candidate-id", default="latest")
    policy_review.add_argument("--decision", choices=["approve", "reject"], required=True)
    policy_review.add_argument("--note", default="")
    policy_review.add_argument("--json", action="store_true")
    policy_apply = policy_sub.add_parser("apply", help="Apply an approved policy candidate")
    policy_apply.add_argument("--project-root", type=Path, default=default_project_root())
    policy_apply.add_argument("--candidate-id", default="latest")
    policy_apply.add_argument("--note", default="")
    policy_apply.add_argument("--json", action="store_true")
    policy_rollback = policy_sub.add_parser("rollback", help="Roll back the live promotion policy")
    policy_rollback.add_argument("--project-root", type=Path, default=default_project_root())
    policy_rollback.add_argument("--target", default="previous")
    policy_rollback.add_argument("--note", default="")
    policy_rollback.add_argument("--json", action="store_true")

    candidate = subparsers.add_parser("candidate", help="Stage and promote corpus candidates")
    candidate_sub = candidate.add_subparsers(dest="action", required=True)
    candidate_show = candidate_sub.add_parser("show", help="Show a corpus candidate manifest")
    candidate_show.add_argument("--project-root", type=Path, default=default_project_root())
    candidate_show.add_argument("--candidate-id", default="latest")
    candidate_show.add_argument("--json", action="store_true")
    candidate_history = candidate_sub.add_parser("history", help="Show corpus candidate history")
    candidate_history.add_argument("--project-root", type=Path, default=default_project_root())
    candidate_history.add_argument("--json", action="store_true")
    candidate_stage = candidate_sub.add_parser(
        "stage", help="Stage a candidate corpus against the live baseline"
    )
    candidate_stage.add_argument("--project-root", type=Path, default=default_project_root())
    candidate_stage.add_argument("--candidate-root", type=Path, required=True)
    candidate_stage.add_argument("--live-corpus-id")
    candidate_stage.add_argument(
        "--provider", choices=["claude", "gemini", "grok", "perplexity", "copilot"]
    )
    candidate_stage.add_argument("--note", default="")
    candidate_stage.add_argument("--json", action="store_true")
    candidate_review = candidate_sub.add_parser("review", help="Review a staged corpus candidate")
    candidate_review.add_argument("--project-root", type=Path, default=default_project_root())
    candidate_review.add_argument("--candidate-id", default="latest")
    candidate_review.add_argument("--decision", choices=["approve", "reject"], required=True)
    candidate_review.add_argument("--note", default="")
    candidate_review.add_argument("--json", action="store_true")
    candidate_promote = candidate_sub.add_parser(
        "promote", help="Promote an approved corpus candidate"
    )
    candidate_promote.add_argument("--project-root", type=Path, default=default_project_root())
    candidate_promote.add_argument("--candidate-id", default="latest")
    candidate_promote.add_argument("--note", default="")
    candidate_promote.add_argument("--json", action="store_true")
    candidate_rollback = candidate_sub.add_parser(
        "rollback", help="Roll back the most recent corpus promotion"
    )
    candidate_rollback.add_argument("--project-root", type=Path, default=default_project_root())
    candidate_rollback.add_argument("--target", default="previous")
    candidate_rollback.add_argument("--note", default="")
    candidate_rollback.add_argument("--json", action="store_true")

    evaluation = subparsers.add_parser("evaluation", help="Seed and run corpus evaluation")
    evaluation_sub = evaluation.add_subparsers(dest="action", required=True)
    evaluation_run = evaluation_sub.add_parser("run", help="Run evaluation for a corpus root")
    evaluation_run.add_argument("--root", type=Path, required=True)
    evaluation_run.add_argument("--seed", action="store_true")
    evaluation_run.add_argument("--markdown-output", type=Path)
    evaluation_run.add_argument("--json-output", type=Path)
    evaluation_run.add_argument("--json", action="store_true")

    review = subparsers.add_parser("review", help="Inspect and resolve federated review items")
    review_sub = review.add_subparsers(dest="action", required=True)
    review_queue = review_sub.add_parser("queue", help="Show the current federated review queue")
    review_queue.add_argument("--project-root", type=Path, default=default_project_root())
    review_queue.add_argument("--json", action="store_true")
    review_queue.add_argument("--limit", type=int, default=50)
    review_history = review_sub.add_parser("history", help="Show resolved federated review history")
    review_history.add_argument("--project-root", type=Path, default=default_project_root())
    review_history.add_argument("--json", action="store_true")
    review_history.add_argument("--limit", type=int, default=50)
    review_resolve = review_sub.add_parser("resolve", help="Resolve a federated review item")
    review_resolve.add_argument("review_id")
    review_resolve.add_argument("--project-root", type=Path, default=default_project_root())
    review_resolve.add_argument(
        "--decision", choices=["accepted", "rejected", "deferred"], required=True
    )
    review_resolve.add_argument("--note", required=True)
    review_resolve.add_argument("--canonical-subject")

    source = subparsers.add_parser("source", help="Inspect source freshness")
    source_sub = source.add_subparsers(dest="action", required=True)
    source_freshness = source_sub.add_parser("freshness", help="Compute corpus source freshness")
    source_freshness.add_argument("corpus_root", type=Path)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.group == "corpus" and args.action == "list":
        corpora = list_registered_corpora(args.project_root)
        if args.json:
            print(json.dumps(corpora, indent=2))
            return
        for entry in corpora:
            marker = "*" if entry.get("default") else "-"
            print(
                f"{marker} {entry['corpus_id']}: {entry['name']} [{entry.get('status', 'active')}]"
            )
            print(f"  root: {entry['root']}")
        return

    if args.group == "corpus" and args.action == "register":
        entry = upsert_corpus(
            args.project_root,
            args.corpus_root,
            corpus_id=args.corpus_id,
            name=args.name,
            make_default=args.default,
        )
        print(json.dumps(entry, indent=2))
        return

    if args.group == "federation" and args.action == "build":
        result = build_federation(args.project_root)
        print(json.dumps(result, indent=2))
        return

    if args.group == "migration" and args.action == "seed-from-staging":
        result = seed_registry_from_staging(
            args.project_root,
            args.staging_root,
            prefer_default=args.prefer_default,
        )
        print(json.dumps(result, indent=2))
        return

    if args.group == "provider" and args.action == "discover":
        source_drop_root = args.source_drop_root or default_source_drop_root(args.project_root)
        result = discover_provider_uploads(args.project_root, source_drop_root)
        if args.json:
            print(json.dumps(result, indent=2))
            return
        print(render_provider_discovery_text(result))
        return

    if args.group == "provider" and args.action == "readiness":
        source_drop_root = args.source_drop_root or default_source_drop_root(args.project_root)
        result = build_provider_readiness(args.project_root, source_drop_root)
        if args.write:
            report_paths = write_provider_readiness_reports(args.project_root, result)
            result = {**result, "report_paths": report_paths}
        if args.json:
            print(json.dumps(result, indent=2))
            return
        print(render_provider_readiness_text(result))
        return

    if args.group == "provider" and args.action == "import":
        result = import_provider_corpus(
            project_root=args.project_root,
            provider=args.provider,
            mode=args.mode,
            source_drop_root=args.source_drop_root,
            source_path=args.source_path,
            local_root=args.local_root,
            output_root=args.output_root,
            corpus_id=args.corpus_id,
            name=args.name,
            register=args.register,
            build=args.build,
            bootstrap_eval=not args.no_bootstrap_eval,
        )
        print(json.dumps(result, indent=2))
        return

    if args.group == "provider" and args.action == "bootstrap-eval":
        payload = bootstrap_provider_evaluation(
            project_root=args.project_root,
            provider=args.provider,
            target_root=args.target_root,
            policy_path=args.policy_path,
            full_eval=args.full_eval,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "provider" and args.action == "refresh":
        payload = refresh_provider_corpus(
            project_root=args.project_root,
            provider=args.provider,
            mode=args.mode,
            source_drop_root=args.source_drop_root,
            source_path=args.source_path,
            local_root=args.local_root,
            live_corpus_id=args.live_corpus_id,
            candidate_root=args.candidate_root,
            bootstrap_eval=not args.no_bootstrap_eval,
            run_eval=not args.no_eval,
            approve=args.approve or args.promote,
            promote=args.promote,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "schema" and args.action == "list":
        payload = {"count": len(SCHEMA_CATALOG), "schemas": list_schemas()}
        if args.json:
            print(json.dumps(payload, indent=2))
            return
        for entry in payload["schemas"]:
            print(f"- {entry['name']}: {entry['description']}")
            print(f"  path: {entry['path']}")
        return

    if args.group == "schema" and args.action == "show":
        payload = {
            "name": args.schema_name,
            "description": SCHEMA_CATALOG[args.schema_name]["description"],
            "path": str(schema_path(args.schema_name)),
            "schema": load_schema(args.schema_name),
        }
        print(json.dumps(payload if args.json else payload["schema"], indent=2))
        return

    if args.group == "schema" and args.action == "validate":
        payload = validate_json_file(args.schema_name, args.path)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            status = "PASS" if payload["valid"] else "FAIL"
            print(f"{status} {args.schema_name} {payload['path']}")
            for issue in payload["errors"]:
                print(f"- {issue['path']}: {issue['message']}")
        if not payload["valid"]:
            raise SystemExit(1)
        return

    if args.group == "surface" and args.action == "manifest":
        payload = build_surface_manifest(
            args.project_root,
            source_drop_root=args.source_drop_root,
        )
        artifacts = write_surface_manifest_artifacts(args.project_root, payload)
        print(json.dumps({**payload, "artifacts_written": artifacts}, indent=2))
        return

    if args.group == "surface" and args.action == "context":
        payload = build_mcp_context_payload(
            args.project_root,
            source_drop_root=args.source_drop_root,
        )
        artifacts = write_mcp_context_artifacts(args.project_root, payload)
        print(json.dumps({**payload, "artifacts_written": artifacts}, indent=2))
        return

    if args.group == "surface" and args.action == "bundle":
        payload = export_surface_bundle(
            args.project_root,
            source_drop_root=args.source_drop_root,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "source-policy" and args.action == "show":
        payload = load_source_policy(args.project_root, args.provider)
        print(json.dumps(payload, indent=2))
        return

    if args.group == "source-policy" and args.action == "set":
        payload = set_source_policy(
            args.project_root,
            args.provider,
            primary_root=args.primary_root,
            primary_corpus_id=args.primary_corpus_id,
            fallback_root=args.fallback_root,
            fallback_corpus_id=args.fallback_corpus_id,
            decision=args.decision,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "source-policy" and args.action == "history":
        path = source_policy_history_path(args.project_root)
        payload = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {"generated_at": None, "count": 0, "items": []}
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "policy" and args.action == "show":
        payload = load_or_create_promotion_policy(args.project_root)
        print(json.dumps(payload, indent=2))
        return

    if args.group == "policy" and args.action == "replay":
        payload = build_policy_replay_payload(
            args.project_root,
            threshold_overrides=parse_threshold_overrides(args.set_threshold) or None,
        )
        if args.write:
            payload = {
                **payload,
                "artifacts": write_policy_replay_artifacts(args.project_root, payload),
            }
        print(json.dumps(payload, indent=2))
        return

    if args.group == "policy" and args.action == "stage":
        payload = stage_policy_candidate(
            args.project_root,
            threshold_overrides=parse_threshold_overrides(args.set_threshold),
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "policy" and args.action == "review":
        payload = review_policy_candidate(
            args.project_root,
            args.candidate_id,
            decision=args.decision,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "policy" and args.action == "apply":
        payload = apply_policy_candidate(
            args.project_root,
            args.candidate_id,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "policy" and args.action == "rollback":
        payload = rollback_policy_application(
            args.project_root,
            target=args.target,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "candidate" and args.action == "show":
        payload = load_corpus_candidate_manifest(args.project_root, candidate_id=args.candidate_id)
        print(json.dumps(payload, indent=2))
        return

    if args.group == "candidate" and args.action == "history":
        path = corpus_candidate_history_path(args.project_root)
        payload = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {"generated_at": None, "count": 0, "items": []}
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "candidate" and args.action == "stage":
        payload = stage_corpus_candidate(
            args.project_root,
            candidate_root=args.candidate_root,
            live_corpus_id=args.live_corpus_id,
            provider=args.provider,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "candidate" and args.action == "review":
        payload = review_corpus_candidate(
            args.project_root,
            args.candidate_id,
            decision=args.decision,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "candidate" and args.action == "promote":
        payload = promote_corpus_candidate(
            args.project_root,
            args.candidate_id,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "candidate" and args.action == "rollback":
        payload = rollback_corpus_promotion(
            args.project_root,
            target=args.target,
            note=args.note,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.group == "evaluation" and args.action == "run":
        scorecard, outputs = run_corpus_evaluation(
            args.root,
            seed=args.seed,
            markdown_output=args.markdown_output,
            json_output=args.json_output,
        )
        payload = {
            "root": str(args.root.resolve()),
            "outputs": {key: str(value) for key, value in outputs.items()},
            "scorecard": scorecard,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
            return
        print(json.dumps(payload["outputs"], indent=2))
        return

    if args.group == "review" and args.action == "queue":
        result = load_federated_review_queue(args.project_root)
        if args.json:
            print(json.dumps(result, indent=2))
            return
        items = [item for item in result.get("items", []) if item.get("status") == "open"]
        print(f"Open review items: {len(items)}")
        for item in items[: max(args.limit, 0)]:
            print(f"- {item['review_id']} [{item['review_type']}] score={item.get('score')}")
        if len(items) > max(args.limit, 0):
            print(f"... {len(items) - max(args.limit, 0)} more")
        return

    if args.group == "review" and args.action == "history":
        result = load_federated_review_history(args.project_root)
        if args.json:
            print(json.dumps(result, indent=2))
            return
        print(f"Resolved review items: {len(result.get('items', []))}")
        for item in result.get("items", [])[: max(args.limit, 0)]:
            print(f"- {item['review_id']} [{item['decision']}] {item.get('recorded_at')}")
        if len(result.get("items", [])) > max(args.limit, 0):
            print(f"... {len(result.get('items', [])) - max(args.limit, 0)} more")
        return

    if args.group == "review" and args.action == "resolve":
        result = resolve_federated_review_item(
            args.project_root,
            args.review_id,
            args.decision,
            args.note,
            canonical_subject=args.canonical_subject,
        )
        print(json.dumps(result, indent=2))
        return

    if args.group == "source" and args.action == "freshness":
        result = compute_source_freshness(args.corpus_root)
        print(json.dumps(result, indent=2))
        return

    parser.error("unsupported command")


if __name__ == "__main__":
    main()
