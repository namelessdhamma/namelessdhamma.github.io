export type PingPayload = {
  ok: true;
  service: "nd-notebooklm-remote-mcp";
  mode: "transport-qualification";
  version: "0.1.0";
};

export function buildPingPayload(): PingPayload {
  return {
    ok: true,
    service: "nd-notebooklm-remote-mcp",
    mode: "transport-qualification",
    version: "0.1.0",
  };
}
