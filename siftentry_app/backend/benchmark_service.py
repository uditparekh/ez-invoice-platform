"""Replay immutable confirmed PDFs through the real extraction pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import replace

from .ai_parser import AiExtractorConfig
from .extraction_benchmarks import (
    compare,
    extraction_revision,
    field_values,
    scope_key,
    CONTRACT_VERSION,
)
from .models import ClientProfile
from .parser_service import parse_pdf_invoice
from .storage import StoredDocument


def cleanup_benchmark_pdfs(app, profile_id=None):
    """Keep a durable removal queue until storage confirms the PDF is absent."""
    started = time.monotonic()
    for row in app.state.repository.pending_benchmark_deletions(profile_id):
        if time.monotonic() - started >= 10:
            break
        try:
            document = StoredDocument(**json.loads(row["storage_json"]))
            app.state.storage.delete(document)
            app.state.storage.read(document)
        except FileNotFoundError:
            app.state.repository.confirm_benchmark_pdf_deleted(row["id"])
        except Exception:
            logging.getLogger(__name__).warning(
                "Benchmark PDF removal pending for %s", row["id"]
            )


def execute_benchmark(app, job):
    repo = app.state.repository
    profile = ClientProfile.model_validate(job.payload["profile"])
    if profile.organization_id != job.organization_id:
        raise ValueError("Benchmark organization mismatch")
    config = app.state.ai_extractor_config
    include_ai = job.payload["include_ai"]
    if include_ai and not config.live_provider:
        raise ValueError(
            "AI provider is unavailable. Run parser-only checks or configure the provider."
        )
    if include_ai and config.status() != job.payload["provider_config"]:
        raise ValueError("AI configuration changed while queued. Start a new check.")
    results = []
    run_started = time.monotonic()
    active = {s["id"]: s for s in repo.benchmark_samples(profile.id)}
    for snapshot in job.payload["samples"]:
        current_job = repo.get_job(job.id)
        if not current_job or current_job.status != "running":
            return {"cancelled": True}
        row = {
            "sample_id": snapshot["id"],
            "filename": snapshot["filename"],
            "split": snapshot["split"],
            "scope_key": scope_key(snapshot["scope"]),
            "review_seconds": snapshot["review_seconds"],
        }
        start = time.monotonic()
        try:
            if time.monotonic() - run_started >= 240:
                raise ValueError(
                    "Benchmark time budget exhausted; remaining samples are not passes"
                )
            sample = active.get(snapshot["id"])
            if not sample:
                raise ValueError("Sample was deleted after this run was queued")
            content = app.state.storage.read(
                StoredDocument(**json.loads(sample["storage_json"]))
            )
            if hashlib.sha256(content).hexdigest() != snapshot["file_hash"]:
                raise ValueError("Stored PDF does not match the confirmed sample")

            # Learning cases cannot retrieve their own lessons; held-out cases
            # can only receive anchors from separate learning documents.
            def resolver(scope, reasons):
                lessons = [
                    l
                    for l in job.payload["lessons"]
                    if l["scope_key"] == scope_key(scope)
                    and l["sample_id"] != snapshot["id"]
                ]
                return {
                    "lessons": [
                        {k: l[k] for k in ("id", "field", "anchor", "relation")}
                        for l in lessons
                    ],
                    "reasons": reasons,
                    "allow_skip": False,
                }

            base = parse_pdf_invoice(
                filename=sample["filename"],
                pdf_bytes=content,
                organization_id=profile.organization_id,
                legal_names=job.payload["legal_names"],
                parser_mode="auto",
                client_profile=profile,
                ai_config=AiExtractorConfig(provider="disabled"),
                learning_resolver=resolver,
            )
            row["baseline"] = compare(snapshot["expected"], field_values(base))
            if include_ai:
                if repo.get_job(job.id).status != "running":
                    return {"cancelled": True}
                assisted = parse_pdf_invoice(
                    filename=sample["filename"],
                    pdf_bytes=content,
                    organization_id=profile.organization_id,
                    legal_names=job.payload["legal_names"],
                    parser_mode="ai",
                    client_profile=profile,
                    ai_config=replace(config, policy="review_only"),
                    learning_resolver=resolver,
                )
                doc = assisted.raw_payload.get("INVOICE", assisted.raw_payload).get(
                    "DOCUMENT", {}
                )
                suggestions = doc.get("AI/OCR SUGGESTIONS") or {}
                values = {
                    k: v.get("value")
                    for k, v in suggestions.items()
                    if isinstance(v, dict)
                }
                values["lines"] = [
                    {
                        "description": l.get("description"),
                        "quantity": l.get("quantity"),
                        "uom": l.get("uom"),
                        "unit_price": l.get("unit_price"),
                        "net_amount": l.get("amount"),
                        "tax_amount": l.get("tax_amount"),
                        "total_amount": l.get("total_amount"),
                        "hsn_sac": l.get("hsn_sac"),
                    }
                    for l in suggestions.get("lines", [])
                ]
                row["ai"] = compare(snapshot["expected"], values)
                row["ai"]["error"] = doc.get("AI/OCR ERROR", "")
                row["ai"]["model"] = doc.get("AI/OCR MODEL", "")
                row["ai"]["latency_ms"] = doc.get("AI/OCR LATENCY MS")
            row["routing"] = base.raw_payload["_extraction_routing"]
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Benchmark sample %s failed (%s)", snapshot["id"], type(exc).__name__
            )
            row["error"] = (
                "Sample could not be evaluated. Check PDF availability and extraction diagnostics."
            )
        row["elapsed_ms"] = round((time.monotonic() - start) * 1000)
        results.append(row)
    summary = {}
    for split in ("learning", "held_out"):
        selected = [r for r in results if r["split"] == split]
        summary[split] = {
            "documents": len(selected),
            "errors": sum(bool(r.get("error")) for r in selected),
        }
        for channel in ("baseline", "ai"):
            measurements = [r[channel] for r in selected if channel in r]
            checks = sum(r["checked"] for r in measurements)
            matches = sum(r["matches"] for r in measurements)
            summary[split][channel] = {
                "measured_documents": len(measurements),
                "passed_documents": sum(r["passed"] for r in measurements),
                "matched_fields": matches,
                "checked_fields": checks,
                "accuracy": round(matches / checks, 4) if checks else None,
            }
    return {
        "contract": CONTRACT_VERSION,
        "revision": job.payload["revision"],
        "extraction_revision": job.payload["extraction_revision"],
        "source_commit": os.getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
        "provider_config": job.payload["provider_config"],
        "include_ai": include_ai,
        "samples": results,
        "summary": summary,
        "current": repo.extraction_revision_number(profile.id)
        == job.payload["revision"]
        and extraction_revision(repo.get_client_profile(profile.id) or profile)
        == job.payload["extraction_revision"],
    }
