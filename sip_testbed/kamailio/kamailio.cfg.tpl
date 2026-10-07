#!KAMAILIO
# BVI testbed proxy. Placeholders (__X__) are filled in by entrypoint.sh per container.
debug=2
log_stderror=yes
children=4
listen=udp:__IP__:5060          # the container's own IP: it is written into Record-Route and Via
auto_aliases=yes
mpath="__MPATH__"

loadmodule "kex.so"
loadmodule "corex.so"
loadmodule "tm.so"
loadmodule "sl.so"
loadmodule "rr.so"
loadmodule "pv.so"
loadmodule "maxfwd.so"
loadmodule "textops.so"
loadmodule "siputils.so"
loadmodule "xlog.so"
loadmodule "exec.so"

modparam("tm", "fr_timer", 8000)
modparam("tm", "fr_inv_timer", 30000)

request_route {
    if (!mf_process_maxfwd_header("10")) { sl_send_reply("483", "Too Many Hops"); exit; }

    if (has_totag()) {                                   # in-dialog: ACK, BYE
        if (loose_route()) { t_relay(); exit; }
        if (is_method("ACK")) { if (t_check_trans()) { t_relay(); } exit; }
        xlog("L_WARN", "hop __HOP__: in-dialog $rm not routed (no Route for me); R-URI $ru\n");
        sl_send_reply("404", "Not here"); exit;
    }
    if (is_method("CANCEL")) { if (t_check_trans()) { t_relay(); } exit; }

    if (is_method("INVITE")) {
        record_route();
        if ($hdr(X-BVI) == "1") { route(BVI); }
    }
    $du = "sip:__NEXT__:5060";
    if (!t_relay()) { sl_reply_error(); }
    exit;
}

# Hop __HOP__ (__NAME__). The caller ID travels in P-Asserted-Identity.
route[BVI] {
    $var(in) = $(ai{uri.user});
    $var(out) = $var(in);

    # Compromised hop: in the 'rewrite' scenario it changes the caller ID and does not attest.
    if (__MALICIOUS__ == 1 && $hdr(X-Scenario) == "rewrite") {
        $var(out) = "__REWRITE_TO__";
        remove_hf("P-Asserted-Identity");
        append_hf("P-Asserted-Identity: <sip:__REWRITE_TO__@bvi.test>\r\n");
        xlog("L_NOTICE", "hop __HOP__ REWROTE caller ID $var(in) -> $var(out); not attesting\n");
        return;
    }
    if (__ATTEST__ == 1) {
        exec_avp("/opt/bvi/attest.sh '$hdr(X-BVI-SID)' __HOP__ '$hdr(X-BVI-DID)' '$var(in)' '$var(out)'", "$avp(ams)");
        append_hf("X-BVI-Attest-Ms: __HOP__=$avp(ams)\r\n");
        xlog("L_INFO", "hop __HOP__ attested $var(in) -> $var(out) in $avp(ams) ms\n");
    }
}
