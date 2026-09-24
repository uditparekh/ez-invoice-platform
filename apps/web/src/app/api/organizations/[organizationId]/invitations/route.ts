import { authenticatedApiRequest } from "@/lib/server/api";
import { NextResponse } from "next/server";

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
  const response = await authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/invitations`,
    {
      method: "POST",
      body: await request.text(),
    },
  );
  const payload = await response.json();
  delete payload.invitation_token;
  return NextResponse.json(payload, {
    status: response.status,
    headers: response.headers,
  });
}
