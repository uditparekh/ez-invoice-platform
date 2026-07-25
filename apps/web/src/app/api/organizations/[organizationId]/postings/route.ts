import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET(
  request: Request,
  context: { params: Promise<{ organizationId: string }> },
) {
  const { organizationId } = await context.params;
  const limit = new URL(request.url).searchParams.get("limit") ?? "200";
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/postings?limit=${encodeURIComponent(limit)}`,
  );
}
