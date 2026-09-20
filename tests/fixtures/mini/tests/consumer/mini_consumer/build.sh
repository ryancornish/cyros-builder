#!/usr/bin/env bash
# Fixture only. Stands in for a real consumer's build: it produces something
# runnable at the declared path, and nothing else.
set -e
mkdir -p out/bin
printf '#!/bin/sh\nexit 0\n' > out/bin/main
chmod +x out/bin/main
