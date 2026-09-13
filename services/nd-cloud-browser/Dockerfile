FROM mcr.microsoft.com/playwright:v1.63.0-noble

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

COPY server.js ./

RUN mkdir -p /data/profile /data/ledger \
    && chown -R pwuser:pwuser /app /data

USER pwuser

ENV NODE_ENV=production
ENV ND_CLOUD_BROWSER_PROFILE_DIR=/data/profile
ENV ND_CLOUD_BROWSER_LEDGER_DIR=/data/ledger

EXPOSE 3000

CMD ["npm", "start"]
