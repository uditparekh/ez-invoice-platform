import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET(
  _request: Request,
  context: { params: Promise<{ organizationId: string }> },
) {
  const { organizationId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/supplier-formats`,
  );
}
