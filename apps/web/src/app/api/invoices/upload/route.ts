import { authenticatedApiRequest } from "@/lib/server/api";

export async function POST(request: Request) {
  const query = new URL(request.url).searchParams.toString();
  return authenticatedApiRequest(`/api/v1/invoices/upload?${query}`, {
    method: "POST",
    body: await request.formData(),
  });
}
