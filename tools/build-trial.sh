#!/bin/zsh
# Build trial: can a coding agent with the bare skills (in .agents/skills/, as `npx skills add` installs them)
# take an ordinary request to working, ledger-enforced code, and how fast? Each run gets a fresh copy of a
# small app in tools/build-trial/<task>/ and its TASK.md as the prompt; no Fragment account; 30 minutes.
# Codex runs with a clean home (tools/codex-home.sh) in its workspace-write sandbox with network on (installs, localhost), as a user who allows installs; Cursor's agent runs with --force (unsandboxed) in the temp folder.
#   tools/build-trial.sh <out-dir> [runs=1] [tasks...]
R=${0:a:h:h}; OUT=${1:?out dir}; N=${2:-1}; shift $(( $# < 2 ? $# : 2 ))
TASKS=($@); (( $#TASKS )) || TASKS=(credits-py budgets-ts); LIMIT=1800
mkdir -p $OUT
source $R/tools/codex-home.sh; CH=$(codex_home $OUT)   # no global MCP servers, hooks or skills
# one copy per results folder: a second copy would rerun the unfinished runs into the same files
mkdir $OUT/.running 2>/dev/null || { echo "another build-trial is using $OUT (remove $OUT/.running if it isn't)"; exit 1; }
source $R/tools/cursor-skills.sh   # after the lock: a copy that exits on it never moves the skill
trap 'rmdir $OUT/.running 2>/dev/null; cursor_skills_restore' EXIT INT TERM
cursor_skills_aside   # Cursor's agent runs without the user's browser skill
run() { # agent task i
  local o=$OUT/$1-$2-$3; [ -e $o/answer.md ] && return
  mkdir -p $o; local W=$(mktemp -d)/app
  cp -R $R/tools/build-trial/$2 $W && mkdir -p $W/.agents/skills && cp -R $R/plugins/fragment/skills/* $W/.agents/skills/ \
    && [ -s $W/TASK.md ] || { echo "$1 $2 $3: setup failed, not run"; rm -rf $o; return; }
  local p=$(<$W/TASK.md); rm $W/TASK.md
  (cd $W && git init -q && git add -A && git -c user.email=t@example.com -c user.name=t commit -qm seed)
  local t0=$(date +%s)
  cd $W || { echo "$1 $2 $3: no workdir, not run"; rm -rf $o; return; }
  if [ $1 = codex ]; then HOME=$CH/home CODEX_HOME=$CH perl -e 'alarm shift; exec @ARGV' $LIMIT codex exec -s workspace-write -c sandbox_workspace_write.network_access=true --skip-git-repo-check \
      --json -o $o/answer.md "$p" < /dev/null > $o/events.jsonl 2> $o/stderr.log
  else perl -e 'alarm shift; exec @ARGV' $LIMIT cursor-agent -p --trust --force --output-format stream-json "$p" \
      < /dev/null > $o/events.jsonl 2> $o/stderr.log
  fi
  local rc=$? t1=$(date +%s)
  cd $R    # leave the run folder first, so the cleanup below can't match this script
  for pid in $(lsof -t +D $W 2>/dev/null | sort -u); do [ $pid != $$ ] && kill $pid 2>/dev/null; done   # servers left running
  echo "{\"agent\":\"$1\",\"task\":\"$2\",\"run\":$3,\"exit\":$rc,\"seconds\":$((t1-t0)),\"start\":$t0,\"workdir\":\"$W\"}" > $o/run.json
  (cd $W && git add -A >/dev/null 2>&1; git diff --cached --stat > $o/diffstat.txt; git diff --cached > $o/diff.patch)
  [ -s $o/answer.md ] || echo "(no answer file; see events.jsonl)" > $o/answer.md
  echo "$1 $2 $3 exit $rc $((t1-t0))s"
}
for agent in codex cursor; do for t in $TASKS; do for i in $(seq 1 $N); do run $agent $t $i & done; done; done; wait
