import os
import subprocess
from typing import Mapping

import click


@click.group()
def cli():
    pass


@cli.command("name")
@click.argument("image")
def mirror_name(image: str):
    name = to_mirror_name(image)
    print(f"original: {image}")
    print(f"copied  : {name}")


@cli.command()
@click.argument("image")
@click.option("--local-git-repo", default="./docker-mirror")
@click.option("--git-bin", default="git")
@click.option("--push/--no-push", "push",  default=True)
def copy(image: str,
         local_git_repo: str = './docker-mirror',
         git_bin: str = 'git',
         push: bool = True,
         ):
    code = f'FROM {image}'
    git_subpath = image.replace(':', '/')
    file_path = os.path.join(git_subpath, "Dockerfile")
    write_file(os.path.join(local_git_repo, file_path), code)

    git = Git(git_bin=git_bin,
              cwd=local_git_repo,
              )

    git.add(file_path)
    git.commit(f"[Add] {image}", False)
    git.push()


def mkdir(path: str):
    if os.path.exists(path):
        return
    parent = os.path.dirname(path)
    if not os.path.exists(parent):
        mkdir(os.path.dirname(path))
    return os.mkdir(path)


def write_file(path: str, content: str):
    mkdir(os.path.dirname(path))
    with open(path, "wt") as f:
        f.write(content)


def to_mirror_name(image: str):
    s = image
    s = s.replace("/", "_")
    s = s.replace(":", "_")
    return s


class Git:

    def __init__(self,
                 git_bin: str = 'git',
                 cwd: str = '.',
                 env: Mapping[str, str] = None,
                 ):
        self.git_bin = git_bin
        self.cwd = cwd
        self.env = env

    def add(self, filepath: str, check: bool = True):
        return self._execute("add", filepath, check=check)

    def commit(self, message: str, check: bool = True):
        return self._execute("commit", "-m", message, check=check)

    def push(self, check: bool = True):
        return self._execute("push", check=check)

    def _execute(self, *args, check: bool = True):
        subprocess.run(
            [self.git_bin, *args],
            cwd=self.cwd,
            env=self.env,
            check=check,
        )


if __name__ == '__main__':
    cli(auto_envvar_prefix='MIRROR_OP')
