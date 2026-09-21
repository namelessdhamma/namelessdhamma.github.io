const RAILWAY_CALLBACK = "https://nd-external-intelligence-production.up.railway.app/drive/oauth/callback";

export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const target = new URL(RAILWAY_CALLBACK);
  for (const key of ["code", "state", "error", "error_description", "scope"]) {
    const value = incoming.searchParams.get(key);
    if (value) target.searchParams.set(key, value);
  }
  return Response.redirect(target.toString(), 302);
}
