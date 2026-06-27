import { authenticatedApiRequest } from "@/lib/server/api";

type RouteContext = {
  params: Promise<{ organizationId: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { organizationId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/members`,
  );
}
