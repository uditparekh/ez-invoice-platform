import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET(
  request: Request,
  context: { params: Promise<{ invoiceId: string }> },
) {
  const { invoiceId } = await context.params;
  const query = new URL(request.url).searchParams.toString();
  return authenticatedApiRequest(
    `/api/v1/invoices/${invoiceId}/profile-recommendations${query ? `?${query}` : ""}`,
  );
}
