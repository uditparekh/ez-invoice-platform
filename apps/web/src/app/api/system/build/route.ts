import { NextResponse } from "next/server";

// Never cached: the whole point is that an installed PWA can ask "is the
// deployment I'm running still the current one?" and get a truthful answer.
export const dynamic = "force-dynamic";
export const revalidate = 0;

// Resolved once per server process. On Vercel this is the deployed commit, so
// every push produces a new value. Locally it falls back to process start time,
// which changes on each dev server restart.
const BUILD_ID =
  process.env.NEXT_PUBLIC_BUILD_ID ||
  process.env.VERCEL_GIT_COMMIT_SHA ||
  process.env.VERCEL_DEPLOYMENT_ID ||
  `dev-${Date.now()}`;

export async function GET() {
  return NextResponse.json(
    { build_id: BUILD_ID },
    {
      headers: {
        "Cache-Control": "no-store, no-cache, must-revalidate",
      },
    },
  );
}
