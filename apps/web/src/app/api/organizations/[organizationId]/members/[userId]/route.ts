import { authenticatedApiRequest } from "@/lib/server/api";

type RouteContext = {
  params: Promise<{ organizationId: string; userId: string }>;
};

export async function PATCH(request: Request, context: RouteContext) {
  const { organizationId, userId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/members/${userId}`,
    {
      method: "PATCH",
      body: await request.text(),
    },
  );
}
