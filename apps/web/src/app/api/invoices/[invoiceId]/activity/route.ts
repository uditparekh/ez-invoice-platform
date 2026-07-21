import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET(
  _request: Request,
  context: { params: Promise<{ invoiceId: string }> },
) {
  const { invoiceId } = await context.params;
  return authenticatedApiRequest(`/api/v1/invoices/${invoiceId}/activity`);
}
