import { authenticatedApiRequest } from "@/lib/server/api";

type RouteContext = {
  params: Promise<{ organizationId: string; profileId: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { organizationId, profileId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/client-profiles/${profileId}/connector-credentials`,
  );
}
