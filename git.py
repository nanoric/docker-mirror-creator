import subprocess
from typing import Mapping


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

    def tag(self, check: bool = True):
        return self._execute("tag", check=check)

    def _execute(self, *args, check: bool = True):
        subprocess.run(
            [self.git_bin, *args],
            cwd=self.cwd,
            env=self.env,
            check=check,
        )
