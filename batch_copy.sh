#!/usr/bin/env bash

#export MIRROR_OP_BUILD_LOCAL_GIT_REPO=/c/projects/docker-mirror

# input : image:tag
my_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
while read image; do
    python $my_dir/mirror-op.py copy --no-commit --no-push --debug $image $@
done
