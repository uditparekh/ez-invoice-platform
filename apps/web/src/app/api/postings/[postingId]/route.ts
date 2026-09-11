import { authenticatedApiRequest } from "@/lib/server/api";
export async function GET(
  _request: Request,
  context: { params: Promise<{ postingId: string }> },
) {
  const { postingId } = await context.params;
  return authenticatedApiRequest(
    `/api/v1/postings/${encodeURIComponent(postingId)}`,
  );
}
