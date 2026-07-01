import { authenticatedApiRequest } from "@/lib/server/api";

export async function POST(
  _request: Request,
  context: { params: Promise<{ organizationId: string; profileId: string }> },
) {
  const { organizationId, profileId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/client-profiles/${profileId}/recommend-settings`,
    { method: "POST" },
  );
}
