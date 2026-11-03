#!/usr/bin/env bash
# Regression tests for image-scan.sh (RD-34). No network, no secrets: curl is stubbed.
# Run: .github/scripts/image-scan.test.sh   (needs bash + jq)
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPT=$HERE/image-scan.sh
FIX=$HERE/fixtures
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# curl stub: records the body, fails when CURL_FAIL=1.
mkdir "$WORK/bin"
cat > "$WORK/bin/curl" <<'STUB'
#!/usr/bin/env bash
cat > "$STUB_DIR/body"
echo "$*" > "$STUB_DIR/args"
[ "${CURL_FAIL:-}" = "1" ] && exit 22
exit 0
STUB
chmod +x "$WORK/bin/curl"

export PATH="$WORK/bin:$PATH" STUB_DIR="$WORK"
export IMAGE_REF=ghcr.io/example/img:tag RUN_URL=https://github.com/example/repo/actions/runs/1

pass=0 fail=0
check() { # name, condition exit status
  if [ "$2" -eq 0 ]; then pass=$((pass + 1)); echo "ok   $1"; else fail=$((fail + 1)); echo "FAIL $1"; fi
}

# Run the script in a clean scratch dir; sets RC, OUTPUT (GITHUB_OUTPUT), LOG (stdout+stderr).
run() {
  rm -rf "$WORK/run" "$WORK/body" "$WORK/args"; mkdir "$WORK/run"
  : > "$WORK/run/output"; : > "$WORK/run/summary"
  ( cd "$WORK/run" && GITHUB_OUTPUT=$WORK/run/output GITHUB_STEP_SUMMARY=$WORK/run/summary "$SCRIPT" "$@" ) > "$WORK/run/log" 2>&1
  RC=$?
  OUTPUT=$(cat "$WORK/run/output"); LOG=$(cat "$WORK/run/log")
}
has() { grep -qF -- "$2" <<< "$1"; }

export SLACK_SECURITY_WEBHOOK_URL=https://hooks.invalid/secret-not-real

# --- clean scans
run summarise "$FIX/clean.json"
check "clean: succeeds with count=0" "$([ $RC -eq 0 ] && has "$OUTPUT" "count=0"; echo $?)"
run summarise "$FIX/clean-null-vulns.json"
check "clean (null Vulnerabilities): count=0" "$([ $RC -eq 0 ] && has "$OUTPUT" "count=0"; echo $?)"

# --- findings
run summarise "$FIX/findings.json"
check "findings: count=7" "$([ $RC -eq 0 ] && has "$OUTPUT" "count=7"; echo $?)"
first=$(sed -n 1p "$WORK/run/findings.txt"); second=$(sed -n 2p "$WORK/run/findings.txt")
check "findings: CRITICAL listed first" "$(has "$first" "(CRITICAL)" && has "$second" "(CRITICAL)"; echo $?)"
check "findings: Slack control chars escaped" "$(has "$(cat "$WORK/run/findings.txt")" "c&lt;&amp;&gt;d"; echo $?)"

cp "$WORK/run/findings.txt" "$WORK/findings.txt"
run notify-findings 7 "$WORK/findings.txt"
body=$(cat "$WORK/body" 2>/dev/null)
check "findings: posted to webhook" "$([ $RC -eq 0 ] && has "$(cat "$WORK/args")" "hooks.invalid"; echo $?)"
check "findings: message has image, count and run link" \
  "$(has "$body" "$IMAGE_REF" && has "$body" "7 CRITICAL/HIGH" && has "$body" "$RUN_URL"; echo $?)"
check "findings: top five only, then '2 more'" \
  "$(has "$body" "…and 2 more" && [ "$(jq -r .text <<< "$body" | grep -c '^•')" -eq 5 ]; echo $?)"

# --- scan could not run
run notify-error
body=$(cat "$WORK/body" 2>/dev/null)
check "error: distinct 'could not run' message with run link" \
  "$([ $RC -eq 0 ] && has "$body" "could not run" && has "$body" "$RUN_URL"; echo $?)"
check "error: output notification=error" "$(has "$OUTPUT" "notification=error"; echo $?)"

# --- report-parsing failures must fail, not look clean
run summarise "$FIX/malformed.txt"
check "malformed report: step fails" "$([ $RC -ne 0 ] && echo 0 || echo 1)"
run summarise "$FIX/wrong-schema.json"
check "non-Trivy JSON: step fails, no count" "$([ $RC -ne 0 ] && ! has "$OUTPUT" "count="; echo $?)"
run summarise "$WORK/does-not-exist.json"
check "missing report: step fails" "$([ $RC -ne 0 ] && echo 0 || echo 1)"

# --- delivery problems stay visible
( unset SLACK_SECURITY_WEBHOOK_URL; run notify-error
  echo "$RC" > "$WORK/rc"; echo "$LOG" > "$WORK/logcopy" )
check "no webhook: exits non-zero with ::error::" "$([ "$(cat "$WORK/rc")" -ne 0 ] && grep -q '::error::.*NOT delivered' "$WORK/logcopy"; echo $?)"
CURL_FAIL=1 run notify-error
check "curl failure: step fails" "$([ $RC -ne 0 ] && echo 0 || echo 1)"

# --- dry run
DRY_RUN=1 run notify-error
check "dry run: no curl call, exits 0, summary written" \
  "$([ $RC -eq 0 ] && [ ! -e "$WORK/args" ] && has "$(cat "$WORK/run/summary")" "could not run"; echo $?)"
( unset SLACK_SECURITY_WEBHOOK_URL; DRY_RUN=1 run notify-findings 7 "$WORK/findings.txt"
  echo "$RC" > "$WORK/rc"; echo "$OUTPUT" > "$WORK/outcopy" )
check "dry run: works without a webhook and reports notification=findings" \
  "$([ "$(cat "$WORK/rc")" -eq 0 ] && grep -q 'notification=findings' "$WORK/outcopy"; echo $?)"

# --- usage
run bogus
check "unknown subcommand: exit 2" "$([ $RC -eq 2 ] && echo 0 || echo 1)"

echo; echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
