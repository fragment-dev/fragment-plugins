#!/bin/zsh
# Runs tools/loop1_tests.py with the user's Cursor browser skill held aside. See that file for the tests.
HERE=${0:a:h}
source $HERE/cursor-skills.sh
cursor_skills_aside; trap cursor_skills_restore EXIT INT TERM
python3 $HERE/loop1_tests.py "$@"
