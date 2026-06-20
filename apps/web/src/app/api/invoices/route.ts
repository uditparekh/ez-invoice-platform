import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.toString();
  return authenticatedApiRequest(`/api/v1/invoices?${query}`);
}
