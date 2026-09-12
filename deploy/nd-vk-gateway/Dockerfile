FROM node:22-alpine

RUN apk add --no-cache python3 ca-certificates
WORKDIR /app

COPY deploy/nd-vk-gateway/runtime-dependency-lock.v1.json /app/runtime-dependency-lock.v1.json
COPY deploy/nd-vk-gateway/vendor_runtime.py /app/vendor_runtime.py
RUN python3 /app/vendor_runtime.py --lock /app/runtime-dependency-lock.v1.json --out /app/vendor

COPY deploy/nd-vk-gateway/run_broker.mjs /app/run_broker.mjs
COPY deploy/nd-vk-gateway/run_gateway.py /app/run_gateway.py
COPY deploy/nd-vk-gateway/start.py /app/start.py
COPY deploy/nd-vk-gateway/audit_runtime_bootstrap.py /app/audit_runtime_bootstrap.py

# Runtime tree itself must not acquire executable code or OS packages.
RUN python3 /app/audit_runtime_bootstrap.py /app

ENV ND_VK_VENDOR_ROOT=/app/vendor
CMD ["python3", "-u", "/app/start.py"]
