import { authenticatedApiRequest } from "@/lib/server/api";

export async function POST(
  request: Request,
  context: { params: Promise<{ organizationId: string }> },
) {
  const { organizationId } = await context.params;
  const body = await request.json().catch(() => ({}));
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/jobs/post-ready`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}
