"""Read-only workspace reporting. Never infer events from current invoice status."""
from __future__ import annotations

import base64
import binascii
import csv
import io
import json
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal


def report_period(start: date | None, end: date | None) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    end = end or today
    start = start or end.replace(day=1)
    if start > end:
        raise ValueError("Start date must be on or before end date.")
    if (end - start).days > 3660:
        raise ValueError("Choose a date range of ten years or less.")
    return (datetime.combine(start, time.min, timezone.utc).isoformat(),
            datetime.combine(end + timedelta(days=1), time.min, timezone.utc).isoformat())


def safe_csv(rows: list[list]) -> str:
    """Quote delimiters/newlines and neutralize spreadsheet formula injection."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    for row in rows:
        writer.writerow([
            "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
            for value in row
        ])
    return output.getvalue()


class ReportingRepository:
    def workspace_analytics(self, organization_id: str, start: str, end: str) -> dict:
        # Read lightweight records, not full invoices/line items. Decimal aggregation
        # avoids compounding binary float errors and has no browser page-size cap.
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, currency, total, tax_total, supplier_json, status, created_at "
                "FROM invoices WHERE organization_id = ? AND created_at >= ? AND created_at < ?",
                (organization_id, start, end),
            ).fetchall()
            queue = connection.execute(
                "SELECT status, COUNT(*) AS count FROM invoices WHERE organization_id = ? GROUP BY status",
                (organization_id,),
            ).fetchall()
            outcomes = connection.execute(
                "SELECT status, COUNT(*) AS count FROM posting_attempts WHERE organization_id = ? "
                "AND dry_run = 0 AND status IN ('succeeded', 'failed') AND updated_at >= ? AND updated_at < ? GROUP BY status",
                (organization_id, start, end),
            ).fetchall()
        currencies = {}
        suppliers = {}
        daily = Counter()
        statuses = Counter()
        for row in rows:
            currency = (row['currency'] or 'UNSPECIFIED').upper()
            total = Decimal(str(row['total']))
            tax = Decimal(str(row['tax_total']))
            bucket = currencies.setdefault(currency, {"currency": currency, "count": 0, "total": Decimal(0), "tax": Decimal(0), "posted_total": Decimal(0)})
            bucket['count'] += 1
            bucket['total'] += total
            bucket['tax'] += tax
            if row['status'] == 'posted':
                bucket['posted_total'] += total
            supplier = json.loads(row['supplier_json']).get('name') or 'Supplier not recorded'
            key = (supplier, currency)
            vendor = suppliers.setdefault(key, {"supplier": supplier, "currency": currency, "count": 0, "total": Decimal(0)})
            vendor['count'] += 1
            vendor['total'] += total
            daily[row['created_at'][:10]] += 1
            statuses[row['status']] += 1
        def amounts(bucket):
            return {key: str(value) if isinstance(value, Decimal) else value for key, value in bucket.items()}
        return {
            "start": start[:10], "end": (datetime.fromisoformat(end) - timedelta(days=1)).date().isoformat(),
            "timezone": "UTC", "generated_at": datetime.now(timezone.utc).isoformat(),
            "received_count": len(rows), "supplier_count": len({key[0] for key in suppliers}),
            "currencies": [amounts(currencies[key]) for key in sorted(currencies)],
            "suppliers": [amounts(value) for _, value in sorted(suppliers.items())],
            "daily": [{"date": key, "count": daily[key]} for key in sorted(daily)],
            "cohort_statuses": dict(statuses),
            "queue": {row['status']: row['count'] for row in queue},
            "posting_outcomes": {row['status']: row['count'] for row in outcomes},
        }

    def workspace_events(self, organization_id: str, start: str, end: str, *,
                         category: str = "all", search: str = "", limit: int = 50,
                         cursor: str | None = None, snapshot: str | None = None) -> dict:
        snapshot = snapshot or datetime.now(timezone.utc).isoformat()
        try:
            parsed = datetime.fromisoformat(snapshot)
            if parsed.tzinfo is None:
                raise ValueError()
            snapshot = parsed.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            raise ValueError("Invalid history snapshot.")
        clauses = ["e.organization_id = ?", "e.created_at >= ?", "e.created_at < ?", "e.created_at <= ?"]
        params = [organization_id, start, end, snapshot]
        if category != 'all':
            clauses.append("e.event_type LIKE ?")
            params.append(category + '.%')
        if search:
            clauses.append("(LOWER(COALESCE(i.invoice_number, '')) LIKE ? ESCAPE '!' OR LOWER(e.event_type) LIKE ? ESCAPE '!')")
            escaped = search.lower().replace('!', '!!').replace('%', '!%').replace('_', '!_')
            params.extend(['%' + escaped + '%'] * 2)
        base_where = ' AND '.join(clauses)
        base_params = list(params)
        if cursor:
            try:
                at, event_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if not isinstance(at, str) or not isinstance(event_id, str):
                    raise ValueError()
                datetime.fromisoformat(at)
            except (ValueError, TypeError, binascii.Error, UnicodeError):
                raise ValueError("Invalid history cursor.")
            clauses.append("(e.created_at < ? OR (e.created_at = ? AND e.id < ?))")
            params.extend([at, at, event_id])
        join = " FROM audit_events e LEFT JOIN invoices i ON i.id = e.invoice_id AND i.organization_id = e.organization_id "
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS count" + join + "WHERE " + base_where, tuple(base_params)).fetchone()['count']
            rows = connection.execute(
                "SELECT e.*, i.invoice_number" + join + "WHERE " + ' AND '.join(clauses) + " ORDER BY e.created_at DESC, e.id DESC LIMIT ?",
                tuple(params + [limit + 1]),
            ).fetchall()
            # Safe allowlist only: raw audit details can contain profile secrets,
            # document paths, or payloads that must not reach read-only members.
            items = []
            for row in rows[:limit]:
                details = json.loads(row['details_json'])
                actor_id = details.get('actor_id')
                actor = None
                if actor_id:
                    user = connection.execute("SELECT full_name FROM users WHERE id = ?", (actor_id,)).fetchone()
                    actor = user['full_name'] if user else 'Recorded service / removed member'
                safe = {key: details[key] for key in ('status', 'fields', 'target', 'dry_run', 'posting_id', 'deleted') if key in details}
                items.append({"id": row['id'], "event_type": row['event_type'], "created_at": row['created_at'],
                              "invoice_id": row['invoice_id'], "invoice_number": row['invoice_number'],
                              "actor": actor, "details": safe})
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = base64.urlsafe_b64encode(json.dumps([last['created_at'], last['id']]).encode()).decode()
        return {"items": items, "next_cursor": next_cursor, "snapshot": snapshot, "total": total}
