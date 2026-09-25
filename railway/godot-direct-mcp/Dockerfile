FROM node:24-bookworm-slim

ARG GODOT_VERSION=4.7.2
ARG GODOT_SHA256=129f82db7bafd54ae14bb5bb284041c73860e8c7a009a3a026ca5e946cbff247
ARG GODOT_MCP_COMMIT=735bdc9c98806e5ecdd05b819bc4ac461d9af935
ARG SUPERGATEWAY_VERSION=4.0.0

ENV DEBIAN_FRONTEND=noninteractive \
    DOTNET_ROOT=/usr/share/dotnet \
    GODOT_PATH=/usr/local/bin/godot \
    GODOT_PROJECT=/workspace/sinee-more-godot \
    GODOT_MCP_DOCS_CACHE=/tmp/nd-godot-docs \
    LIBGL_ALWAYS_SOFTWARE=1
ENV PATH="/usr/share/dotnet:${PATH}"

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates curl git unzip xvfb ffmpeg procps \
    libx11-6 libxcursor1 libxinerama1 libxrandr2 libxi6 libxkbcommon0 \
    libgl1 libegl1 libvulkan1 libasound2 libpulse0 libfontconfig1 libudev1 libdbus-1-3 \
    libicu72 libssl3 zlib1g \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet \
    && rm /tmp/dotnet-install.sh \
    && dotnet --version

RUN curl -fL "https://github.com/godotengine/godot-builds/releases/download/${GODOT_VERSION}-stable/Godot_v${GODOT_VERSION}-stable_mono_linux_x86_64.zip" -o /tmp/godot.zip \
    && echo "${GODOT_SHA256}  /tmp/godot.zip" | sha256sum -c - \
    && mkdir -p /opt/godot \
    && unzip -q /tmp/godot.zip -d /opt/godot \
    && GODOT_BIN="$(find /opt/godot -type f -name 'Godot_v*-stable_mono_linux.x86_64' -print -quit)" \
    && test -n "$GODOT_BIN" \
    && chmod +x "$GODOT_BIN" \
    && ln -sf "$GODOT_BIN" /usr/local/bin/godot \
    && rm /tmp/godot.zip \
    && godot --version

RUN git clone --quiet https://github.com/blentz/godot-mcp.git /opt/godot-mcp \
    && git -C /opt/godot-mcp checkout --quiet "${GODOT_MCP_COMMIT}" \
    && npm --prefix /opt/godot-mcp ci \
    && npm --prefix /opt/godot-mcp run build \
    && test -f /opt/godot-mcp/dist/server.js

RUN npm install -g "supergateway@${SUPERGATEWAY_VERSION}"

COPY sinee-more-godot /workspace/sinee-more-godot
COPY railway/godot-direct-mcp/start.sh /usr/local/bin/nd-godot-start

RUN chmod +x /usr/local/bin/nd-godot-start \
    && mkdir -p /workspace/sinee-more-godot/addons \
    && cp -R /opt/godot-mcp/addon/godot_mcp /workspace/sinee-more-godot/addons/godot_mcp

WORKDIR /workspace/sinee-more-godot

EXPOSE 8080

CMD ["/usr/local/bin/nd-godot-start"]
