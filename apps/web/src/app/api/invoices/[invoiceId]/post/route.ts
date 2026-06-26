import { authenticatedApiRequest } from "@/lib/server/api";

export async function POST(
  request: Request,
  context: { params: Promise<{ invoiceId: string }> },
) {
  const { invoiceId } = await context.params;
  return authenticatedApiRequest(`/api/v1/invoices/${invoiceId}/post`, {
    method: "POST",
    body: await request.text(),
  });
}
