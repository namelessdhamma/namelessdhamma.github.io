# ND Telegram Publisher Reserve

Independent reserve runtime for @NamelessDhamma Telegram publishing.

- Source authority: GitHub.
- Runtime: Render, independent from Railway.
- Transport: Streamable HTTP MCP.
- Secret values are runtime environment variables only and must not be committed.
- Production channel: @NamelessDhamma.
- Tools: status, send/edit/delete text, photo, video.
- Deletion requires confirm=true.
- Writes are controlled by ND_TELEGRAM_WRITES_ENABLED.

This reserve is intentionally small and does not depend on the primary Railway provider gateway.
