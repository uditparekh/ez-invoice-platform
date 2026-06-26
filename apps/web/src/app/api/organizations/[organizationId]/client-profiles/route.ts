import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET(
  request: Request,
  context: { params: Promise<{ organizationId: string }> },
) {
  const { organizationId } = await context.params;
  const query = new URL(request.url).searchParams.toString();
  const suffix = query ? `?${query}` : "";
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/client-profiles${suffix}`,
  );
}

export async function POST(
  request: Request,
  context: { params: Promise<{ organizationId: string }> },
) {
  const { organizationId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/client-profiles`,
    {
      method: "POST",
      body: await request.text(),
    },
  );
}
