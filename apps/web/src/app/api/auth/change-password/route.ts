import { authenticatedApiRequest } from "@/lib/server/api";

export async function POST(request: Request) {
  return authenticatedApiRequest("/api/v1/auth/change-password", {
    method: "POST",
    body: await request.text(),
  });
}
