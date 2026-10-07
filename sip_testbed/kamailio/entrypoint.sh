#!/bin/sh
set -e
IP=$(hostname -i | awk '{print $1}')
echo "proxy $NAME (hop $HOP) on $IP, next $NEXT, attest=${ATTEST:-1}, malicious=${MALICIOUS:-0}"
MPATH=$(dirname "$(find /usr/lib -path '*kamailio/modules/tm.so' | head -1)")/
sed -e "s#__IP__#$IP#" -e "s#__MPATH__#$MPATH#" -e "s#__NEXT__#$NEXT#" -e "s#__HOP__#$HOP#g" -e "s#__NAME__#$NAME#" \
    -e "s#__ATTEST__#${ATTEST:-1}#" -e "s#__MALICIOUS__#${MALICIOUS:-0}#" -e "s#__REWRITE_TO__#${REWRITE_TO:-none}#g" \
    /opt/bvi/kamailio.cfg.tpl > /etc/kamailio/bvi.cfg
kamailio -c -f /etc/kamailio/bvi.cfg
mkdir -p /var/run/kamailio
exec kamailio -DD -E -f /etc/kamailio/bvi.cfg
