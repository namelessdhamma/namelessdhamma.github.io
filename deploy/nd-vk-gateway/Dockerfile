FROM node:22-alpine AS vendor_builder
RUN apk add --no-cache python3 ca-certificates
WORKDIR /build
COPY deploy/nd-vk-gateway/runtime-dependency-lock.v1.json /build/runtime-dependency-lock.v1.json
COPY deploy/nd-vk-gateway/vendor_runtime.py /build/vendor_runtime.py
RUN python3 /build/vendor_runtime.py --lock /build/runtime-dependency-lock.v1.json --out /vendor

FROM node:22-alpine
RUN apk add --no-cache python3 ca-certificates
WORKDIR /app
COPY --from=vendor_builder /vendor /app/vendor
COPY deploy/nd-vk-gateway/run_broker.mjs /app/run_broker.mjs
COPY deploy/nd-vk-gateway/run_gateway.py /app/run_gateway.py
COPY deploy/nd-vk-gateway/start.py /app/start.py
COPY deploy/nd-vk-gateway/audit_runtime_bootstrap.py /app/audit_runtime_bootstrap.py
COPY deploy/nd-vk-gateway/context_memory.py /app/context_memory.py
COPY deploy/nd-vk-gateway/context_memory_store.py /app/context_memory_store.py
COPY deploy/nd-vk-gateway/context_gateway.py /app/context_gateway.py

# Runtime filesystem must contain no raw-GitHub bootstrap or package installer.
RUN python3 /app/audit_runtime_bootstrap.py /app
RUN python3 -m py_compile /app/context_memory.py /app/context_memory_store.py /app/context_gateway.py /app/run_gateway.py /app/start.py

ENV ND_VK_VENDOR_ROOT=/app/vendor
CMD ["python3", "-u", "/app/start.py"]
