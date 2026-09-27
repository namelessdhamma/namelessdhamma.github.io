FROM node:24-bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ ca-certificates && rm -rf /var/lib/apt/lists/*

COPY package.json ./
RUN npm install --omit=dev

COPY . .

CMD ["node", "memos_front.mjs"]
