# Sourced by the test scripts: a clean Codex home for test runs, so the user's own MCP servers, hooks, plugins
# and skills (a browser, computer use, connectors) never reach the agent under test. Keeps only the model
# settings, and links the sign-in rather than copying it.
#   codex_home <dir>   -> prints the path to use as CODEX_HOME
codex_home() {
  local h=$1/codex-home
  mkdir -p $h && chmod 700 $h
  [ -e $h/auth.json ] || ln -s ${CODEX_HOME:-$HOME/.codex}/auth.json $h/auth.json
  grep -E '^(model|model_reasoning_effort|model_provider) *=' ${CODEX_HOME:-$HOME/.codex}/config.toml > $h/config.toml 2>/dev/null
  echo $h
}
