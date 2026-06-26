import { authenticatedApiRequest } from "@/lib/server/api";

export async function POST(
  _request: Request,
  context: { params: Promise<{ invoiceId: string }> },
) {
  const { invoiceId } = await context.params;
  return authenticatedApiRequest(`/api/v1/invoices/${invoiceId}/validate`, {
    method: "POST",
  });
}
