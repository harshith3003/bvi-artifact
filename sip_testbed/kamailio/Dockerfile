FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends kamailio curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY sip_testbed/kamailio/kamailio.cfg.tpl sip_testbed/kamailio/attest.sh sip_testbed/kamailio/entrypoint.sh /opt/bvi/
RUN chmod +x /opt/bvi/*.sh
ENTRYPOINT ["/opt/bvi/entrypoint.sh"]
