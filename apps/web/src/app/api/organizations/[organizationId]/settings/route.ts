import { authenticatedApiRequest } from "@/lib/server/api";

type RouteContext = {
  params: Promise<{ organizationId: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { organizationId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/settings`,
  );
}

export async function PUT(request: Request, context: RouteContext) {
  const { organizationId } = await context.params;
  const body = await request.json();
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/settings`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}
