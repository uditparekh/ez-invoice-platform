import { authenticatedApiRequest } from "@/lib/server/api";
export async function GET(
  request: Request,
  context: { params: Promise<{ organizationId: string }> },
) {
  const { organizationId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${encodeURIComponent(organizationId)}/events/export?${new URL(request.url).searchParams}`,
  );
}
