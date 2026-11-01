# Sourced by the test scripts: keeps the user's global Cursor browser skill away from Cursor's agent while tests
# run, by moving it to a holding folder and putting it back when the last running test script exits.
#   cursor_skills_aside; trap cursor_skills_restore EXIT INT TERM
# (set the trap at the script's top level: in zsh a trap set inside a function fires when the function returns)
CURSOR_SKILLS=$HOME/.cursor/skills
CURSOR_HOLD=$HOME/.cursor/skills-held-by-fragment-tests
CURSOR_ASIDE=(aside-browser)

cursor_skills_aside() {
  mkdir -p $CURSOR_HOLD/runs && touch $CURSOR_HOLD/runs/$$
  for s in $CURSOR_ASIDE; do
    [ -e $CURSOR_SKILLS/$s ] && [ ! -e $CURSOR_HOLD/$s ] && mv $CURSOR_SKILLS/$s $CURSOR_HOLD/$s
  done
}

cursor_skills_restore() {
  rm -f $CURSOR_HOLD/runs/$$
  for f in $CURSOR_HOLD/runs/*(N); do kill -0 ${f:t} 2>/dev/null || rm -f $f; done   # forget runs that died
  [ -n "$(ls $CURSOR_HOLD/runs 2>/dev/null)" ] && return                                # another test still running
  for s in $CURSOR_ASIDE; do
    [ -e $CURSOR_HOLD/$s ] && [ ! -e $CURSOR_SKILLS/$s ] && mv $CURSOR_HOLD/$s $CURSOR_SKILLS/$s
  done
  rmdir $CURSOR_HOLD/runs $CURSOR_HOLD 2>/dev/null
  true
}
