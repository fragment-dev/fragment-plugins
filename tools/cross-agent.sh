#!/bin/zsh
# Runs the frozen pick-rate prompts on Codex and Cursor's agent with the bare skills installed in .agents/skills/
# (as `npx skills add` would) and without them. Read-only modes; uses your Codex and Cursor accounts.
#   tools/cross-agent.sh <out-dir> [runs-with=2] [runs-without=1]
set -e
R=${0:a:h:h}; OUT=${1:?out dir}; RW=${2:-2}; RO=${3:-1}
source $R/tools/codex-home.sh; mkdir -p $OUT; CH=$(codex_home $OUT)
W=$(mktemp -d); mkdir -p $W/with/.agents/skills $W/without $OUT
cp -R $R/plugins/fragment/skills/* $W/with/.agents/skills/
for d in with without; do (cd $W/$d && git init -q && echo "# app" > README.md); done
CASES=(choose-credits choose-payouts choose-agent-budgets heldout-game-currency heldout-fastapi-budgets heldout-driver-earnings)
run() { # agent arm case i
  local p=$(python3 -c "import sys;print(open('$R/plugins/fragment/evals/$3/prompt.md').read().split('---',2)[2].strip())")
  local o=$OUT/$1-$2-$3-$4.md; [ -s $o ] && return
  cd $W/$2
  if [ $1 = codex ]; then CODEX_HOME=$CH codex exec -s read-only --skip-git-repo-check --ephemeral -o $o "$p" < /dev/null > $o.log 2>&1
  else cursor-agent -p --trust --mode ask --output-format text "$p" < /dev/null > $o 2> $o.log; fi
  echo "$1 $2 $3 $4 exit $?"
}
for agent in codex cursor; do (
  for c in $CASES; do for i in $(seq 1 $RW); do run $agent with $c $i; done; done
  for c in $CASES; do for i in $(seq 1 $RO); do run $agent without $c $i; done; done
) & done; wait
python3 $R/tools/score.py files $OUT
