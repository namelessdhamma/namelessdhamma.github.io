import { createMcpHandler } from "mcp-handler";
import { z } from "zod";

import { buildPingPayload } from "../../../src/ping";

const handler = createMcpHandler((server) => {
  server.registerTool(
    "nd_ping",
    {
      title: "ND Ping",
      description:
        "Harmless transport qualification check for the ND NotebookLM remote MCP.",
      inputSchema: z.object({}),
    },
    async () => ({
      content: [
        {
          type: "text",
          text: JSON.stringify(buildPingPayload()),
        },
      ],
    }),
  );
});

export { handler as GET, handler as POST };
