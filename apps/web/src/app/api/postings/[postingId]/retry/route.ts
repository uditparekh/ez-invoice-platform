import { authenticatedApiRequest } from "@/lib/server/api";

export async function POST(
  request: Request,
  context: { params: Promise<{ postingId: string }> },
) {
  const { postingId } = await context.params;
  return authenticatedApiRequest(`/api/v1/postings/${postingId}/retry`, {
    method: "POST",
    body: await request.text(),
  });
}
