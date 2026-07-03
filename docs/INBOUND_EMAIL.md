# Inbound Invoice Email

SiftEntry can receive supplier invoice PDFs by email through a trusted webhook
from an email provider. The webhook reuses the same backend invoice processing
path as the browser upload flow.

## Flow

1. Supplier emails a PDF invoice to the configured intake address.
2. The email provider parses the message and calls SiftEntry's inbound endpoint.
3. SiftEntry validates the shared webhook secret.
4. Each PDF attachment is parsed through the same profile-aware invoice intake
   pipeline used by browser upload.
5. The invoice appears in the normal queue for review, approval, and posting.

## Endpoint

```http
POST /api/v1/inbound/email
X-SiftEntry-Inbound-Secret: <shared-secret>
Content-Type: application/json
```

Payload:

```json
{
  "organization_id": "org_...",
  "from_email": "ap@supplier.com",
  "to_email": "invoices@client.siftentry.com",
  "subject": "Invoice INV-1001",
  "message_id": "<provider-message-id>",
  "parser_mode": "auto",
  "client_profile_id": null,
  "attachments": [
    {
      "filename": "invoice.pdf",
      "content_type": "application/pdf",
      "content_base64": "JVBERi0x..."
    }
  ]
}
```

Response:

```json
{
  "organization_id": "org_...",
  "accepted": 1,
  "rejected": 0,
  "invoices": [],
  "errors": []
}
```

The actual response includes the created invoice objects in `invoices`.

## Environment Variables

| Variable | Purpose |
|---|---|
| `SIFTENTRY_INBOUND_EMAIL_SECRET` | Shared secret required by the webhook |
| `SIFTENTRY_INBOUND_EMAIL_ADDRESS` | Optional configured intake address, for docs/health tracking |
| `SIFTENTRY_INBOUND_EMAIL_MAX_ATTACHMENTS` | Attachment limit per webhook request; default `10` |

The endpoint is disabled until `SIFTENTRY_INBOUND_EMAIL_SECRET` is set.

## Storage Policy

Email PDFs follow the same retention rules as uploaded PDFs:

- Default: review-window retention.
- Client profile can disable PDF storage.
- Client profile can enable paid 90-day storage.
- File metadata stores hash, size, retention policy, and delete date.

This keeps email intake cost-controlled and avoids saving original PDFs forever
unless the client paid for that feature.
