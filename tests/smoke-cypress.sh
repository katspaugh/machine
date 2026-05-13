#!/usr/bin/env bash
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

# shellcheck disable=SC2016  # single quotes intentional: script runs inside VM
limactl shell "$NAME" -- bash -lc '
  set -e
  if command -v google-chrome >/dev/null; then BROWSER=chrome; else BROWSER=chromium; fi
  workdir=$(mktemp -d) && cd "$workdir"
  cat > package.json <<EOF
{ "name": "cy-smoke", "private": true }
EOF
  # npm (not pnpm) so cypress postinstall runs (downloads the binary).
  npm install -D cypress >/dev/null
  mkdir -p cypress/e2e
  cat > cypress/e2e/smoke.cy.js <<EOF
describe("smoke", () => {
  it("runs JS and assertions", () => {
    cy.wrap({ ok: true }).its("ok").should("be.true");
    cy.wrap([1, 2, 3]).should("have.length", 3);
  });
});
EOF
  cat > cypress.config.js <<EOF
module.exports = { e2e: { supportFile: false } };
EOF
  npx cypress run --browser "$BROWSER" --headless
'

echo "cypress OK"
