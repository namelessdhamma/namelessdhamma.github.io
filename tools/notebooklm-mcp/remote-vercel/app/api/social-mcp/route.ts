import { createMcpHandler } from "mcp-handler";
import { z } from "zod";

import {
  SOCIAL_PROVIDERS,
  authRequirements,
  invokeSocial,
  readiness,
  type SocialProvider,
} from "../../../src/social";

const Provider = z.enum(SOCIAL_PROVIDERS);

const handler = createMcpHandler((server) => {
  server.registerTool(
    "social_direct_status",
    {
      title: "ND Social Direct Status",
      description:
        "Return direct-route authorization/configuration status for an ND social provider without exposing secrets.",
      inputSchema: z.object({ provider: Provider }),
    },
    async ({ provider }) => ({
      content: [
        {
          type: "text",
          text: JSON.stringify(readiness(provider as SocialProvider)),
        },
      ],
    }),
  );

  server.registerTool(
    "social_direct_auth_requirements",
    {
      title: "ND Social Direct Auth Requirements",
      description:
        "Return bounded provider authorization requirements, callback URL and scopes.",
      inputSchema: z.object({ provider: Provider }),
    },
    async ({ provider }) => ({
      content: [
        {
          type: "text",
          text: JSON.stringify(authRequirements(provider as SocialProvider)),
        },
      ],
    }),
  );

  server.registerTool(
    "social_direct_invoke",
    {
      title: "ND Social Direct Invoke",
      description:
        "Invoke a direct social-provider adapter. Writes fail closed until provider-specific qualification is complete.",
      inputSchema: z.object({
        provider: Provider,
        operation: z.enum([
          "status",
          "account",
          "publish",
          "schedule",
          "edit",
          "delete",
          "metrics",
          "comments",
        ]),
      }),
    },
    async ({ provider, operation }) => {
      try {
        const result = await invokeSocial(
          provider as SocialProvider,
          operation,
        );
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                ok: true,
                provider,
                operation,
                route: "direct_mcp_vercel",
                result,
              }),
            },
          ],
        };
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "unknown_error";
        return {
          isError: true,
          content: [
            {
              type: "text",
              text: JSON.stringify({
                ok: false,
                provider,
                operation,
                route: "direct_mcp_vercel",
                status: message.startsWith("AWAITING_AUTH:")
                  ? "AWAITING_AUTH"
                  : message === "WRITE_NOT_QUALIFIED"
                    ? "WRITE_NOT_QUALIFIED"
                    : "FAILED",
                error: message,
              }),
            },
          ],
        };
      }
    },
  );
});

export { handler as GET, handler as POST };
