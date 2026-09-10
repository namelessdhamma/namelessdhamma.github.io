import { buildPingPayload } from "../../../src/ping";

export async function GET() {
  return Response.json(buildPingPayload(), {
    headers: {
      "cache-control": "no-store",
    },
  });
}
