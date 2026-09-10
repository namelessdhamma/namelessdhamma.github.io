import { describe, expect, it } from "vitest";

import { buildPingPayload } from "../src/ping";

describe("buildPingPayload", () => {
  it("returns the stable Stage-A transport qualification payload", () => {
    expect(buildPingPayload()).toEqual({
      ok: true,
      service: "nd-notebooklm-remote-mcp",
      mode: "transport-qualification",
      version: "0.1.0",
    });
  });
});
