#!/bin/sh
# Local chain (Hardhat node, JSON-RPC on 8545, automine) + the BVI service on 8080.
npx hardhat node --hostname 127.0.0.1 > /tmp/node.log 2>&1 &
until node -e "fetch('http://127.0.0.1:8545',{method:'POST',headers:{'content-type':'application/json'},body:'{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"eth_chainId\",\"params\":[]}'}).then(()=>process.exit(0)).catch(()=>process.exit(1))"; do sleep 1; done
exec npx hardhat run --network localhost service.js
