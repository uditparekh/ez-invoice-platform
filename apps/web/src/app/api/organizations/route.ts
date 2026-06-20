import { authenticatedApiRequest } from "@/lib/server/api";

export async function GET() {
  return authenticatedApiRequest("/api/v1/organizations");
}
