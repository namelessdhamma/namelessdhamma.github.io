FROM node:24-bookworm-slim

ARG GODOT_VERSION=4.7.2
ARG GODOT_SHA256=129f82db7bafd54ae14bb5bb284041c73860e8c7a009a3a026ca5e946cbff247
ARG GODOT_MCP_COMMIT=735bdc9c98806e5ecdd05b819bc4ac461d9af935
ARG TUNNEL_VERSION=0.0.14
ARG TUNNEL_SHA256=15bd17e805cad39d412199115bb9e10a978dd35258a114cdf25dd2ae6681c7d3

ENV DEBIAN_FRONTEND=noninteractive
ENV DOTNET_ROOT=/opt/dotnet
ENV PATH="/opt/dotnet:${PATH}"
ENV DISPLAY=:99

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git unzip xz-utils ffmpeg xvfb \
    libx11-6 libxcursor1 libxinerama1 libxrandr2 libxi6 libxkbcommon0 \
    libgl1 libegl1 libvulkan1 libasound2 libpulse0 libfontconfig1 \
    libudev1 libdbus-1-3 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 8.0 --install-dir /opt/dotnet \
    && rm /tmp/dotnet-install.sh

RUN curl -fL "https://github.com/godotengine/godot-builds/releases/download/${GODOT_VERSION}-stable/Godot_v${GODOT_VERSION}-stable_mono_linux_x86_64.zip" -o /tmp/godot.zip \
    && echo "${GODOT_SHA256}  /tmp/godot.zip" | sha256sum -c - \
    && mkdir -p /opt/godot \
    && unzip -q /tmp/godot.zip -d /opt/godot \
    && GODOT_BIN="$(find /opt/godot -type f -name 'Godot_v*-stable_mono_linux.x86_64' -print -quit)" \
    && test -n "$GODOT_BIN" \
    && chmod +x "$GODOT_BIN" \
    && ln -s "$GODOT_BIN" /usr/local/bin/godot \
    && rm /tmp/godot.zip

RUN git clone https://github.com/blentz/godot-mcp.git /opt/godot-mcp \
    && cd /opt/godot-mcp \
    && git checkout "${GODOT_MCP_COMMIT}" \
    && npm ci \
    && npm run build \
    && npm prune --omit=dev

RUN curl -fL "https://github.com/openai/tunnel-client/releases/download/v${TUNNEL_VERSION}/tunnel-client-v${TUNNEL_VERSION}-linux-amd64.zip" -o /tmp/tunnel.zip \
    && echo "${TUNNEL_SHA256}  /tmp/tunnel.zip" | sha256sum -c - \
    && mkdir -p /tmp/tunnel \
    && unzip -q /tmp/tunnel.zip -d /tmp/tunnel \
    && TUNNEL_BIN="$(find /tmp/tunnel -type f -name tunnel-client -print -quit)" \
    && test -n "$TUNNEL_BIN" \
    && install -m 0755 "$TUNNEL_BIN" /usr/local/bin/tunnel-client \
    && rm -rf /tmp/tunnel /tmp/tunnel.zip

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY . .

RUN chmod +x ./start_all.sh ./godot_sidecar.sh

CMD ["bash", "./start_all.sh"]
