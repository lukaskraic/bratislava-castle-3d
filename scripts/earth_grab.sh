#!/bin/bash
# copy the newest Claude-in-Chrome screenshot to data/ref/earth/<name>.jpg
d=$(ls -dt /var/folders/*/*/T/claude-chrome-screenshots-*/ 2>/dev/null | head -1)
f=$(ls -t "$d"*.jpg | head -1)
cp "$f" "$(dirname "$0")/../data/ref/earth/$1.jpg" && echo "saved $1 <- $(basename "$f")"
