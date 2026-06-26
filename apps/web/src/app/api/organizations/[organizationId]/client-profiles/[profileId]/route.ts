import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET(
  _request: Request,
  context: { params: Promise<{ organizationId: string; profileId: string }> },
) {
  const { organizationId, profileId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/client-profiles/${profileId}`,
  );
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ organizationId: string; profileId: string }> },
) {
  const { organizationId, profileId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/client-profiles/${profileId}`,
    {
      method: "PATCH",
      body: await request.text(),
    },
  );
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ organizationId: string; profileId: string }> },
) {
  const { organizationId, profileId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/client-profiles/${profileId}`,
    { method: "DELETE" },
  );
}
