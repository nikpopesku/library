#!/usr/bin/env bash
# Helpers for .github/workflows/scan.yml (RD-34). Kept out of the YAML so they can be tested
# without a runner or a real Slack webhook (see image-scan.test.sh).
#
#   image-scan.sh summarise <trivy.json>            writes count= to $GITHUB_OUTPUT and findings.txt
#   image-scan.sh notify-findings <count> <file>    Slack alert listing the top five findings
#   image-scan.sh notify-error                      Slack alert: the scan itself could not run
#
# Env: IMAGE_REF, RUN_URL, SLACK_SECURITY_WEBHOOK_URL, GITHUB_OUTPUT (optional),
#      DRY_RUN=1 (print the payload to the step summary instead of posting).
set -euo pipefail

out() { echo "$1" >> "${GITHUB_OUTPUT:-/dev/null}"; }

summarise() {
  local report=$1
  # A report that is missing or not shaped like Trivy output must fail the step rather than count as
  # "0 findings", otherwise a broken scan would look clean.
  if ! jq -e '.SchemaVersion == 2 and (.Results == null or (.Results | type == "array"))' "$report" > /dev/null; then
    echo "::error::$report is not a valid Trivy JSON report; treating the scan as failed."
    return 1
  fi
  local vulns='[.Results[]? | .Vulnerabilities[]?]'
  local count
  count=$(jq "$vulns | length" "$report")
  # CRITICAL first; escape the characters Slack treats as control.
  jq -r "$vulns | sort_by(.Severity != \"CRITICAL\") | .[]
    | \"• \(.VulnerabilityID) \(.PkgName) \(.InstalledVersion) → \(.FixedVersion) (\(.Severity))\"
    | gsub(\"&\"; \"&amp;\") | gsub(\"<\"; \"&lt;\") | gsub(\">\"; \"&gt;\")" "$report" > findings.txt
  cat findings.txt
  out "count=$count"
}

post() {
  local kind=$1 text=$2
  out "notification=$kind"
  if [ "${DRY_RUN:-}" = "1" ]; then
    {
      echo "### Dry run: Slack \`$kind\` notification (not sent)"
      echo
      echo "$text"
    } >> "${GITHUB_STEP_SUMMARY:-/dev/stdout}"
    return 0
  fi
  if [ -z "${SLACK_SECURITY_WEBHOOK_URL:-}" ]; then
    # Fail loudly: a green run must not imply that the alert was delivered.
    echo "::error::SLACK_SECURITY_WEBHOOK_URL is not set; the $kind notification was NOT delivered."
    return 1
  fi
  jq -n --arg text "$text" '{text: $text}' \
    | curl -fsS -X POST -H "Content-type: application/json" --data @- "$SLACK_SECURITY_WEBHOOK_URL"
}

notify_findings() {
  local count=$1 file=$2 text
  text=":warning: Vulnerability scan found $count CRITICAL/HIGH issue(s) in *${IMAGE_REF}*"
  text+=" — <${RUN_URL}|view results>"
  text+=$'\n'"$(head -n 5 "$file")"
  if [ "$count" -gt 5 ]; then
    text+=$'\n'"…and $((count - 5)) more"
  fi
  post findings "$text"
}

notify_error() {
  post error ":x: Image scan could not run for *${IMAGE_REF}* — <${RUN_URL}|view logs>"
}

case "${1:-}" in
  summarise) summarise "${2:?report path}" ;;
  notify-findings) notify_findings "${2:?count}" "${3:?findings file}" ;;
  notify-error) notify_error ;;
  *) echo "usage: $0 summarise <report> | notify-findings <count> <file> | notify-error" >&2; exit 2 ;;
esac
