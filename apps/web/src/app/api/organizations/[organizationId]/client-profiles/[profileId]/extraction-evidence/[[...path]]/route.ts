import { authenticatedApiRequest } from "@/lib/server/api";

type Context = {
  params: Promise<{
    organizationId: string;
    profileId: string;
    path?: string[];
  }>;
};
async function proxy(request: Request, context: Context) {
  const { organizationId, profileId, path = [] } = await context.params;
  const action = path.join("/");
  const allowed =
    request.method === "GET"
      ? action === ""
      : request.method === "POST"
        ? ["samples", "lessons", "runs", "cancel"].includes(action)
        : request.method === "DELETE" &&
          /^(sample|lesson)\/[a-zA-Z0-9-]+$/.test(action);
  if (!allowed)
    return Response.json(
      { detail: "Unknown evidence action." },
      { status: 404 },
    );
  const body =
    request.method === "POST"
      ? action === "samples"
        ? await request.formData()
        : await request.text()
      : undefined;
  return authenticatedApiRequest(
    `/api/v1/organizations/${encodeURIComponent(organizationId)}/client-profiles/${encodeURIComponent(profileId)}/extraction-evidence${action ? `/${action}` : ""}`,
    { method: request.method, body },
  );
}
export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
