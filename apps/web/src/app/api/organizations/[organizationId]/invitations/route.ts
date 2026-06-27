import { authenticatedApiRequest } from "@/lib/server/api";

type RouteContext = {
  params: Promise<{ organizationId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { organizationId } = await context.params;
  const params = new URL(request.url).searchParams;
  const includeAccepted = params.get("include_accepted") === "true";
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/invitations?include_accepted=${includeAccepted}`,
  );
}

export async function POST(request: Request, context: RouteContext) {
  const { organizationId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/invitations`,
    {
      method: "POST",
      body: await request.text(),
    },
  );
}
