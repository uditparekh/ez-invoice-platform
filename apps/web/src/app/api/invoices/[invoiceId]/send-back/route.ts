import { authenticatedApiRequest } from "@/lib/server/api";

export async function POST(
  request: Request,
  context: { params: Promise<{ invoiceId: string }> },
) {
  const { invoiceId } = await context.params;
  const body = await request.json();
  return authenticatedApiRequest(`/api/v1/invoices/${invoiceId}/send-back`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
