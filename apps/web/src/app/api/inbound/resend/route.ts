import { createHmac, timingSafeEqual } from "node:crypto";

import { NextResponse } from "next/server";

/**
 * Resend inbound email -> SiftEntry intake bridge.
 *
 * Resend delivers an `email.received` webhook (Svix-signed) with attachment
 * metadata only. This route verifies the signature, downloads the PDF
 * attachments through Resend's Attachments API, and forwards them to the
 * FastAPI backend's /api/v1/inbound/email endpoint in the payload shape it
 * expects (base64 attachments + X-SiftEntry-Inbound-Secret header).
 *
 * The route is inert until all of these environment variables are set in
 * Vercel (see docs/PILOT_INFRA_CHECKLIST.md):
 *
 *   RESEND_WEBHOOK_SECRET            whsec_... from the Resend webhook page
 *   RESEND_API_KEY                   re_... used to download attachments
 *   SIFTENTRY_INBOUND_EMAIL_SECRET   same value configured on the backend
 *   SIFTENTRY_INBOUND_ORG_MAP        JSON map of intake address -> organization
 *                                    id, e.g. {"invoices-acme@in.siftentry.com":
 *                                    "org_123"}; or set
 *   SIFTENTRY_INBOUND_DEFAULT_ORG    single organization id fallback
 */

const RESEND_API_BASE = "https://api.resend.com";
const API_BASE_URL =
  process.env.EZ_WEB_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";
const SIGNATURE_TOLERANCE_SECONDS = 5 * 60;
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;

type ResendAttachmentMeta = {
  id: string;
  filename?: string;
  content_type?: string;
  download_url?: string;
  size?: number;
};

type ResendInboundEvent = {
  type?: string;
  data?: {
    email_id?: string;
    from?: string;
    to?: string[];
    subject?: string;
    message_id?: string;
    attachments?: ResendAttachmentMeta[];
  };
};

function verifySvixSignature(
  payload: string,
  headers: Headers,
  secret: string,
): boolean {
  const id = headers.get("svix-id");
  const timestamp = headers.get("svix-timestamp");
  const signatureHeader = headers.get("svix-signature");
  if (!id || !timestamp || !signatureHeader) return false;

  const timestampSeconds = Number(timestamp);
  if (!Number.isFinite(timestampSeconds)) return false;
  const skew = Math.abs(Date.now() / 1000 - timestampSeconds);
  if (skew > SIGNATURE_TOLERANCE_SECONDS) return false;

  const secretBytes = Buffer.from(secret.replace(/^whsec_/, ""), "base64");
  const expected = createHmac("sha256", secretBytes)
    .update(`${id}.${timestamp}.${payload}`)
    .digest();

  return signatureHeader.split(" ").some((candidate) => {
    const [, value] = candidate.split(",", 2);
    if (!value) return false;
    const provided = Buffer.from(value, "base64");
    return (
      provided.length === expected.length && timingSafeEqual(provided, expected)
    );
  });
}

function resolveOrganizationId(toAddresses: string[]): string {
  const rawMap = process.env.SIFTENTRY_INBOUND_ORG_MAP ?? "";
  if (rawMap) {
    try {
      const map = JSON.parse(rawMap) as Record<string, string>;
      const normalized = new Map(
        Object.entries(map).map(([address, org]) => [
          address.trim().toLowerCase(),
          org,
        ]),
      );
      for (const address of toAddresses) {
        const match = normalized.get(address.trim().toLowerCase());
        if (match) return match;
      }
    } catch {
      // Malformed map: fall through to the default organization.
    }
  }
  return process.env.SIFTENTRY_INBOUND_DEFAULT_ORG ?? "";
}

async function listAttachments(
  emailId: string,
  apiKey: string,
): Promise<ResendAttachmentMeta[]> {
  const response = await fetch(
    `${RESEND_API_BASE}/emails/receiving/${emailId}/attachments`,
    { headers: { Authorization: `Bearer ${apiKey}` }, cache: "no-store" },
  );
  if (!response.ok) {
    throw new Error(`Resend attachments list failed (${response.status}).`);
  }
  const body = (await response.json()) as { data?: ResendAttachmentMeta[] };
  return body.data ?? [];
}

export async function POST(request: Request) {
  const webhookSecret = process.env.RESEND_WEBHOOK_SECRET ?? "";
  const resendApiKey = process.env.RESEND_API_KEY ?? "";
  const inboundSecret = process.env.SIFTENTRY_INBOUND_EMAIL_SECRET ?? "";

  if (!webhookSecret || !resendApiKey || !inboundSecret) {
    return NextResponse.json(
      { error: "Inbound email bridge is not configured." },
      { status: 503 },
    );
  }

  const payload = await request.text();
  if (!verifySvixSignature(payload, request.headers, webhookSecret)) {
    return NextResponse.json(
      { error: "Invalid webhook signature." },
      { status: 401 },
    );
  }

  let event: ResendInboundEvent;
  try {
    event = JSON.parse(payload) as ResendInboundEvent;
  } catch {
    return NextResponse.json({ error: "Invalid JSON payload." }, { status: 400 });
  }

  if (event.type !== "email.received" || !event.data?.email_id) {
    // Acknowledge unrelated events so Resend does not retry them.
    return NextResponse.json({ ignored: true });
  }

  const toAddresses = event.data.to ?? [];
  const organizationId = resolveOrganizationId(toAddresses);
  if (!organizationId) {
    // Acknowledged but unroutable; visible in Vercel logs for follow-up.
    console.warn(
      `Inbound email ${event.data.email_id} to [${toAddresses.join(", ")}] ` +
        "matched no organization; skipping.",
    );
    return NextResponse.json({ ignored: true, reason: "no_organization_match" });
  }

  let attachmentsMeta: ResendAttachmentMeta[];
  try {
    attachmentsMeta = await listAttachments(event.data.email_id, resendApiKey);
  } catch (error) {
    // 500 so Resend retries; the attachment CDN may not be ready yet.
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Attachment lookup failed." },
      { status: 500 },
    );
  }

  const pdfMeta = attachmentsMeta.filter((attachment) => {
    const name = (attachment.filename ?? "").toLowerCase();
    const type = (attachment.content_type ?? "").toLowerCase();
    return name.endsWith(".pdf") || type === "application/pdf";
  });
  if (pdfMeta.length === 0) {
    return NextResponse.json({ ignored: true, reason: "no_pdf_attachments" });
  }

  const attachments: Array<{
    filename: string;
    content_type: string;
    content_base64: string;
  }> = [];
  for (const attachment of pdfMeta) {
    if (!attachment.download_url) continue;
    if ((attachment.size ?? 0) > MAX_ATTACHMENT_BYTES) continue;
    const download = await fetch(attachment.download_url, { cache: "no-store" });
    if (!download.ok) {
      return NextResponse.json(
        { error: `Attachment download failed (${download.status}).` },
        { status: 500 },
      );
    }
    const bytes = Buffer.from(await download.arrayBuffer());
    if (bytes.length > MAX_ATTACHMENT_BYTES) continue;
    attachments.push({
      filename: attachment.filename || "invoice.pdf",
      content_type: attachment.content_type || "application/pdf",
      content_base64: bytes.toString("base64"),
    });
  }
  if (attachments.length === 0) {
    return NextResponse.json({ ignored: true, reason: "no_usable_attachments" });
  }

  const upstream = await fetch(`${API_BASE_URL}/api/v1/inbound/email`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-SiftEntry-Inbound-Secret": inboundSecret,
    },
    cache: "no-store",
    body: JSON.stringify({
      organization_id: organizationId,
      from_email: event.data.from ?? "",
      to_email: toAddresses[0] ?? "",
      subject: event.data.subject ?? "",
      message_id: event.data.message_id ?? event.data.email_id,
      parser_mode: "auto",
      client_profile_id: null,
      attachments,
    }),
  });

  const body = await upstream.json().catch(() => ({}));
  return NextResponse.json(body, { status: upstream.status });
}
