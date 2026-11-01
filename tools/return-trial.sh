#!/bin/zsh
# Return trial: does a later session keep building on the ledger, or drift to its own tables?
# Takes the apps a build test produced, and gives a fresh agent session (no memory of the first) a change request in
# that same folder, with the skills still installed, like a developer coming back a week later.
#   tools/return-trial.sh <build-test-dir> <out-dir> [task=credits-py]
R=${0:a:h:h}; SRC=${1:?build test results}; OUT=${2:?out dir}; TASK=${3:-credits-py}; LIMIT=1800
PROMPT='Two changes. Users want refunds of credits they have not used. And we want to give promo credits that expire after 30 days and are spent before purchased credits. Add both. Run it and show it working.'
mkdir -p $OUT
mkdir $OUT/.running 2>/dev/null || { echo "another return-trial is using $OUT"; exit 1; }
source $R/tools/codex-home.sh; CH=$(codex_home $OUT)
source $R/tools/cursor-skills.sh
trap 'rmdir $OUT/.running 2>/dev/null; cursor_skills_restore' EXIT INT TERM
cursor_skills_aside
run() { # run-dir-name
  local name=$1 agent=${1%%-*} o=$OUT/$1; [ -e $o/answer.md ] && return
  local from=$(python3 -c "import json,sys;print(json.load(open('$SRC/$name/run.json'))['workdir'])")
  [ -d $from ] || { echo "$name: its folder is gone"; return; }
  mkdir -p $o; local W=$(mktemp -d)/app; cp -R $from $W
  (cd $W && rm -rf .fragment-local .app-data __pycache__ .venv node_modules; git add -A >/dev/null 2>&1; git -c user.email=t@example.com -c user.name=t commit -qm 'first session' >/dev/null)
  local t0=$(date +%s); cd $W
  if [ $agent = codex ]; then HOME=$CH/home CODEX_HOME=$CH perl -e 'alarm shift; exec @ARGV' $LIMIT codex exec -s workspace-write -c sandbox_workspace_write.network_access=true --skip-git-repo-check \
      --json -o $o/answer.md "$PROMPT" < /dev/null > $o/events.jsonl 2> $o/stderr.log
  else perl -e 'alarm shift; exec @ARGV' $LIMIT cursor-agent -p --trust --force --output-format stream-json "$PROMPT" \
      < /dev/null > $o/events.jsonl 2> $o/stderr.log
  fi
  local rc=$? t1=$(date +%s)
  cd $R
  for pid in $(lsof -t +D $W 2>/dev/null | sort -u); do [ $pid != $$ ] && kill $pid 2>/dev/null; done
  echo "{\"agent\":\"$agent\",\"from\":\"$name\",\"exit\":$rc,\"seconds\":$((t1-t0)),\"workdir\":\"$W\"}" > $o/run.json
  (cd $W && git add -A >/dev/null 2>&1; git diff --cached --stat -- . ':!node_modules' ':!package-lock.json' ':!*.pyc' > $o/diffstat.txt; git diff --cached -- . ':!node_modules' ':!package-lock.json' ':!*.pyc' > $o/diff.patch)
  [ -s $o/answer.md ] || echo "(no answer file; see events.jsonl)" > $o/answer.md
  echo "$name exit $rc $((t1-t0))s | new entry types: $(grep -cE '^\+.*"type": *"[a-z_]+"' $o/diff.patch) | new SQL tables: $(grep -ciE '^\+.*create table' $o/diff.patch) | SDK calls added: $(grep -cE '^\+.*(addLedgerEntry|add_ledger_entry)' $o/diff.patch)"
}
for d in $SRC/*-$TASK-*(/); do run ${d:t} & done; wait
