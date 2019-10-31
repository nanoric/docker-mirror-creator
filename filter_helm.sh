#!/usr/bin/env bash

# input : helm install ... --debug --dry-run
# output: image:tag
grep -P "image: .*:.*"|cut -d ':' -f2,3|tr -d '" '
