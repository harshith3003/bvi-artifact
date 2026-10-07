FROM node:20-bookworm-slim
WORKDIR /app
COPY registry_v2/package.json registry_v2/hardhat.config.js ./
RUN npm install --no-audit --no-fund
COPY registry_v2/contracts ./contracts
COPY registry_v2/test/verifier.js ./test/verifier.js
RUN npx hardhat compile
COPY sip_testbed/bvi/service.js sip_testbed/bvi/entrypoint.sh sip_testbed/bvi/thresholds.json ./
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
