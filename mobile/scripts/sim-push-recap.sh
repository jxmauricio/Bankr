#!/bin/sh
# Show the weekly recap banner on a booted iOS Simulator. Real APNs never
# reaches the Simulator; this injects the same payload the Sunday cron sends.
set -e
DEVICE="${1:-booted}"
PAYLOAD="$(cd "$(dirname "$0")" && pwd)/weekly-recap.push.json"
xcrun simctl push "$DEVICE" com.jxmauricio.bankr "$PAYLOAD"
