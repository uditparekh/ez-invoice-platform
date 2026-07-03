import { authenticatedApiRequest } from "@/lib/server/api";

type RouteContext = {
  params: Promise<{ organizationId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { organizationId } = await context.params;
  const body = await request.json().catch(() => ({}));
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/invoices/post-ready`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}
