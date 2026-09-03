import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET() {
  return authenticatedApiRequest("/api/v1/organizations");
}

export async function POST(request: Request) {
  return authenticatedApiRequest("/api/v1/organizations", {
    method: "POST",
    body: await request.text(),
  });
}
