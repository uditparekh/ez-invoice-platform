import { authenticatedApiRequest, clearAuthCookies } from "@/lib/server/api";

export async function POST(request: Request) {
  const response = await authenticatedApiRequest(
    "/api/v1/auth/change-password",
    {
      method: "POST",
      body: await request.text(),
    },
  );
  if (response.ok) clearAuthCookies(response);
  return response;
}
