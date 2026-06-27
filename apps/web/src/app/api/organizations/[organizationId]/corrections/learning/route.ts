import { authenticatedApiRequest } from "@/lib/server/api";

type RouteContext = {
  params: Promise<{ organizationId: string }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { organizationId } = await context.params;
  const params = new URL(request.url).searchParams;
  const limit = params.get("limit") ?? "100";
  return authenticatedApiRequest(
    `/api/v1/organizations/${organizationId}/corrections/learning?limit=${encodeURIComponent(limit)}`,
  );
}
