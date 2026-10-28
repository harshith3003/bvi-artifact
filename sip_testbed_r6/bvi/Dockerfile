FROM node:20-bookworm-slim
WORKDIR /app
COPY registry_v2/package.json registry_v2/hardhat.config.js ./
RUN npm install --no-audit --no-fund
COPY registry_v2/contracts ./contracts
COPY registry_v2/test/verifier.js registry_v2/test/verifier_r.js ./test/
RUN npx hardhat compile
COPY sip_testbed_r6/bvi/service_r6.js ./service.js
COPY sip_testbed/bvi/entrypoint.sh sip_testbed/bvi/thresholds.json ./
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
