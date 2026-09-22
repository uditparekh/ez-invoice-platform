"""Explicit reviewer consent and scoped access for extraction benchmarks."""

import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError

from .auth import get_current_user
from .extraction_benchmarks import (
    AnchorLesson,
    BenchmarkConfirmation,
    EvaluationRequest,
    extraction_scope,
    extraction_revision,
    normalized,
)
from .models import AuthenticatedUser
from .parser_service import extract_pdf_text
from .storage import StoredDocument

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/client-profiles/{profile_id}/extraction-evidence",
    tags=["extraction-evidence"],
)
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def require_profile(request, org, profile_id, user, write=False):
    from .main import _require_client_profile, READ_ROLES, EDIT_ROLES

    return _require_client_profile(
        request, org, profile_id, user, EDIT_ROLES if write else READ_ROLES
    )


@router.get("")
def view(
    request: Request, organization_id: str, profile_id: str, current_user: CurrentUser
):
    profile = require_profile(request, organization_id, profile_id, current_user)
    repo = request.app.state.repository
    job = repo.latest_benchmark_job(profile)
    revision = repo.extraction_revision_number(profile.id)
    public_job = None
    if job:
        public_job = {
            "id": job.id,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "error": job.error,
            "result": job.result,
            "current": job.payload.get("revision") == revision
            and job.payload.get("extraction_revision") == extraction_revision(profile)
            and (
                not job.payload.get("include_ai")
                or job.payload.get("provider_config")
                == request.app.state.ai_extractor_config.status()
            ),
        }
    samples = [
        {
            k: s[k]
            for k in (
                "id",
                "filename",
                "expected",
                "scope",
                "split",
                "confirmed_by",
                "review_seconds",
                "created_at",
            )
        }
        for s in repo.benchmark_samples(profile.id)
    ]
    return {
        "pending_pdf_deletions": len(repo.pending_benchmark_deletions(profile.id)),
        "samples": samples,
        "lessons": repo.benchmark_lessons(profile.id),
        "revision": revision,
        "job": public_job,
        "ai_available": request.app.state.ai_extractor_config.live_provider,
    }


@router.post("/samples", status_code=201)
async def add_sample(
    request: Request,
    organization_id: str,
    profile_id: str,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
    confirmation: Annotated[str, Form()],
):
    profile = require_profile(request, organization_id, profile_id, current_user, True)
    try:
        body = BenchmarkConfirmation.model_validate_json(confirmation)
    except ValidationError:
        raise HTTPException(
            422,
            "Confirm the expected header and line values, split, and PDF retention consent.",
        )
    content = await file.read(request.app.state.settings.max_upload_bytes + 1)
    if (
        not content
        or len(content) > request.app.state.settings.max_upload_bytes
        or not content.startswith(b"%PDF-")
    ):
        raise HTTPException(422, "Upload a valid PDF within the upload size limit.")
    try:
        text, _, pages = extract_pdf_text(content)
    except ValueError:
        raise HTTPException(
            422, "This PDF has no usable text layer. OCR samples are not supported yet."
        )
    scope = extraction_scope(
        profile.id, body.expected.model_dump(), text, pages, content
    )
    storage = request.app.state.storage
    filename = Path(file.filename or "benchmark.pdf").name
    stored = storage.save(
        organization_id, "benchmark-" + filename, content, "application/pdf"
    )
    try:
        sample_id = request.app.state.repository.add_benchmark(
            profile, stored, filename, content, body, scope, current_user.id
        )
    except Exception:
        storage.delete(stored)
        raise
    return {"id": sample_id}


@router.post("/lessons", status_code=201)
def add_lesson(
    request: Request,
    organization_id: str,
    profile_id: str,
    current_user: CurrentUser,
    body: AnchorLesson,
):
    profile = require_profile(request, organization_id, profile_id, current_user, True)
    repo = request.app.state.repository
    sample = next(
        (
            s
            for s in repo.benchmark_samples(profile.id)
            if s["id"] == body.sample_id and s["split"] == "learning"
        ),
        None,
    )
    if not sample:
        raise HTTPException(
            409,
            "Select an active learning sample. Held-out samples cannot teach the model.",
        )
    try:
        content = request.app.state.storage.read(
            StoredDocument(**json.loads(sample["storage_json"]))
        )
        text, _, _ = extract_pdf_text(content)
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(409, "The source PDF is unavailable. No lesson was saved.")
    anchor = normalized(body.anchor)
    if anchor not in normalized(text) or not any(c.isalpha() for c in anchor):
        raise HTTPException(
            422,
            "The label must appear in the sample PDF. Store a label, not an invoice value.",
        )
    if any(
        anchor == normalized(value)
        for key, value in sample["expected"].items()
        if key != "lines" and value
    ):
        raise HTTPException(422, "Store the field's label, not its confirmed value.")
    return {"id": repo.add_anchor_lesson(profile, sample, body, current_user.id)}


@router.delete("/{kind}/{item_id}")
def delete_item(
    request: Request,
    organization_id: str,
    profile_id: str,
    current_user: CurrentUser,
    kind: Literal["sample", "lesson"],
    item_id: str,
):
    profile = require_profile(request, organization_id, profile_id, current_user, True)
    request.app.state.repository.delete_benchmark_item(
        profile, item_id, kind, current_user.id
    )
    if kind == "sample":
        from .benchmark_service import cleanup_benchmark_pdfs

        cleanup_benchmark_pdfs(request.app, profile.id)
    return {"deleted": True}


@router.post("/runs", status_code=202)
def run_checks(
    request: Request,
    organization_id: str,
    profile_id: str,
    current_user: CurrentUser,
    body: EvaluationRequest,
):
    profile = require_profile(request, organization_id, profile_id, current_user, True)
    repo = request.app.state.repository
    config = request.app.state.ai_extractor_config
    if body.include_ai and not config.live_provider:
        raise HTTPException(
            409, "AI is not configured. Parser-only checks are available."
        )
    job = repo.queue_benchmark(profile, config, body.include_ai, current_user.id)
    return {"id": job.id, "status": job.status}


@router.post("/cancel")
def cancel_check(
    request: Request, organization_id: str, profile_id: str, current_user: CurrentUser
):
    profile = require_profile(request, organization_id, profile_id, current_user, True)
    request.app.state.repository.cancel_benchmark(profile, current_user.id)
    return {"cancelled": True}
