import logging
import os
from asyncio import *
from copy import copy

import click

from aliyun_cr import AliyunCR

logger = logging.getLogger(__file__)


@click.group()
@click.option("--log-level",
              type=click.Choice(['DEBUG', "INFO", "WARNING", "ERROR"]),
              default="INFO")
def cli(
    log_level: str,
):
    logging.basicConfig(level=getattr(logging, log_level))


@cli.command("name")
@click.argument("image")
@click.argument("aliyun-cr-namespace", envvar='MIRROR_OP_CR_NAMESPACE', default='zh-mirror')
@click.argument("aliyun-cr-region", envvar='MIRROR_OP_CR_REGION', default='cn-shanghai')
def cli_mirror_name(
    image: str,
    aliyun_cr_namespace: str = 'zh-mirror',
    aliyun_cr_region: str = 'cn-shanghai',
):
    cr_image = cr_image_name(image=image,
                         cr_namespace=aliyun_cr_namespace,
                         cr_region=aliyun_cr_region,
                         )
    print(f"{image} -> {cr_image}")


@cli.command("copy")
@click.argument("image")
@click.option("--local-git-repo", default="./docker-mirror")
@click.option("--git-bin", default="git")
@click.option("--push/--no-push", "push", default=True)
@click.option("--commit/--no-commit", "commit", default=True)
@click.option("--debug/--no-debug", "debug", default=False)
def cli_copy(image: str,
             local_git_repo: str = './docker-mirror',
             git_bin: str = 'git',
             commit: bool = True,
             push: bool = True,
             debug: bool = False,
             ):
    from git import Git
    code = f'FROM {image}'
    git_sub_path = image.replace(':', '/')
    git_full_path = os.path.join(git_sub_path, "Dockerfile")
    dest = os.path.join(local_git_repo, git_full_path)
    if debug:
        print(f"writting {code} into {dest}")
    write_file(dest, code)

    git = Git(git_bin=git_bin,
              cwd=local_git_repo,
              )

    git.add(git_full_path)
    if commit:
        git.commit(f"[Add] {image}", False)
    if push:
        git.push()


@cli.command("build")
@click.argument("aliyun-cr-access_key", envvar='MIRROR_OP_CR_ACCESS_KEY')
@click.argument("aliyun-cr-access_secret", envvar='MIRROR_OP_CR_ACCESS_SECRET')
@click.argument("aliyun-cr-namespace", envvar='MIRROR_OP_CR_NAMESPACE', default='zh-mirror')
@click.argument("github-namespace", envvar='MIRROR_OP_GITHUB_NAMESPACE',
                default='nanoric-public-cd')
@click.argument("github-repo", envvar='MIRROR_OP_GITHUB_REPO', default='docker-mirror')
@click.option("--aliyun-cr-region", default="cn-shanghai")
@click.option("--local-git-repo", default="./docker-cr_image")
def cli_build(
    **kwargs,
):
    return get_event_loop().run_until_complete(async_cli_build(**kwargs))


def image_from_git_sub_path(git_sub_path: str):
    dirs = git_sub_path.split('/')
    repository = "/".join(dirs[:-1])
    tag = dirs[-1]
    return f'{repository}:{tag}'


async def list_local_repo(
    local_git_repo: str,
):
    for root, dirs, files in os.walk(local_git_repo):
        for file in files:
            if file == "Dockerfile":
                path = os.path.join(root, file)
                dir_name = os.path.dirname(path)
                git_sub_path = os.path.relpath(dir_name, local_git_repo).replace("\\", "/")

                yield git_sub_path


async def async_cli_build(
    aliyun_cr_region: str,
    aliyun_cr_access_key: str,
    aliyun_cr_access_secret: str,
    aliyun_cr_namespace: str,
    github_namespace: str,
    github_repo: str,
    local_git_repo: str = './docker-cr_image',
):
    cr = AliyunCR(
        access_key=aliyun_cr_access_key,
        access_secret=aliyun_cr_access_secret,
        region=aliyun_cr_region,
        namespace=aliyun_cr_namespace,
    )
    cr_repos = {i.name: i async for i in cr.list_repo()}
    logger.debug(f'# of repos : {len(cr_repos)}')
    loop = get_event_loop()

    async def iterate():
        async for git_sub_path in list_local_repo(local_git_repo):
            image = image_from_git_sub_path(git_sub_path)
            tag, repo_name = cr_info(image)
            task = loop.create_task(
                trigger_build(cr, cr_repos, git_sub_path, github_namespace,
                              github_repo, image, repo_name, tag))
            yield image, task

    async for image, task in iterate():
        # noinspection PyBroadException
        try:
            await task
        except Exception as e:
            logging.warning(f"Failed to build {image}: {e}")


async def trigger_build(cr: AliyunCR, cr_repos, git_sub_path, github_namespace,
                        github_repo, image,
                        repo_name, tag):
    log = logger.getChild(image)
    if repo_name not in cr_repos:
        log.info(f"repo {repo_name} not exist, creating ...")
        await cr.create_repo(
            name=repo_name,
            github_namespace=github_namespace,
            github_repo=github_repo,
        )
    else:
        log.debug(f"use existing repo: {repo_name}")
    rules = [i async for i in cr.list_build_rule(repo_name=repo_name)]
    correct_rules = [i for i in rules if i.tag == tag]
    if not correct_rules:
        dockerfile_dir = f'/{git_sub_path}/'
        log.info(f'build rule for tag "{tag}" not exist, creating ... \n')
        log.info(f'creating rule: dockerfile_dir: {dockerfile_dir}, tag: {tag}')
        rule_id = await cr.create_build_rule(
            repo_name=repo_name,
            dockerfile_dir=dockerfile_dir,
            tag=tag,
        )
        log.info(f'trigger the rule just created ...')
        await cr.build_by_rule(repo_name=repo_name, rule_id=rule_id)
    else:
        log.debug(f'rule exist, skip triggering it.')


@cli.command("check")
@click.argument("aliyun-cr-access_key", envvar='MIRROR_OP_CR_ACCESS_KEY')
@click.argument("aliyun-cr-access_secret", envvar='MIRROR_OP_CR_ACCESS_SECRET')
@click.argument("aliyun-cr-namespace", envvar='MIRROR_OP_CR_NAMESPACE', default='zh-mirror')
@click.option("--aliyun-cr-region", default="cn-shanghai")
@click.option("--local-git-repo", default="./docker-cr_image")
def cli_check(
    **kwargs,
):
    return get_event_loop().run_until_complete(async_cli_check(**kwargs))


async def async_cli_check(
    aliyun_cr_region: str,
    aliyun_cr_access_key: str,
    aliyun_cr_access_secret: str,
    aliyun_cr_namespace: str,
    local_git_repo: str = './docker-cr_image',
):
    cr = AliyunCR(
        access_key=aliyun_cr_access_key,
        access_secret=aliyun_cr_access_secret,
        region=aliyun_cr_region,
        namespace=aliyun_cr_namespace,
    )
    cr_repos = {i.name: i async for i in cr.list_repo()}
    logger.debug(f'# of repos : {len(cr_repos)}')
    loop = get_event_loop()

    async def iterate():
        async for git_sub_path in list_local_repo(local_git_repo):
            image = image_from_git_sub_path(git_sub_path)
            tag, repo_name = cr_info(image)
            task = loop.create_task(trigger_check(cr, cr_repos, repo_name, tag))
            yield image, task

    async for image, task in iterate():
        try:
            if await task:
                cr_image = cr_image_name(cr_region=aliyun_cr_region,
                                         cr_namespace=aliyun_cr_namespace,
                                         image=image)
                print(f"{image} -> {cr_image}")
            else:
                print(f"not passed: {image}")
        except Exception as e:
            logger.error(f"Exception on {image}: {e}")


async def trigger_check(cr: AliyunCR, cr_repos,
                        repo_name, tag):
    log = logger.getChild(repo_name)
    if repo_name not in cr_repos:
        log.warning("Repo not exist!")
        return False
    rules = [i async for i in cr.list_build_rule(repo_name=repo_name)]
    correct_rules = [i for i in rules if i.tag == tag]
    if not correct_rules:
        log.warning(f"Rule for {tag} not exist!")
        return False
    tags = [i async for i in cr.list_tags(repo_name=repo_name)]
    if tag not in tags:
        builds = [i async for i in cr.list_not_finished_builds(repo_name=repo_name, tag=tag)]
        if builds:
            log.warning("Tag not exist, build pending or building!")
        else:
            log.warning("Tag not exist, no pending build!")
        return False
    return True


@cli.command("clear")
@click.argument("aliyun-cr-access_key", envvar='MIRROR_OP_CR_ACCESS_KEY')
@click.argument("aliyun-cr-access_secret", envvar='MIRROR_OP_CR_ACCESS_SECRET')
@click.argument("aliyun-cr-namespace", envvar='MIRROR_OP_CR_NAMESPACE', default='zh-mirror')
@click.option("--aliyun-cr-region", default="cn-shanghai")
def cli_clear(
    **kwargs,
):
    return get_event_loop().run_until_complete(async_cli_clear(**kwargs))


async def async_cli_clear(
    aliyun_cr_access_key: str,
    aliyun_cr_access_secret: str,
    aliyun_cr_namespace: str,
    aliyun_cr_region: str,
):
    cr = AliyunCR(
        access_key=aliyun_cr_access_key,
        access_secret=aliyun_cr_access_secret,
        region=aliyun_cr_region,
        namespace=aliyun_cr_namespace,
    )
    cr_repos = {i.name: i async for i in cr.list_repo()}
    logger.debug(f'# of repos : {len(cr_repos)}')
    loop = get_event_loop()

    def _it():
        for repo in cr_repos.values():
            if repo.namespace == aliyun_cr_namespace:
                logger.info(f"deleting {repo.namespace}/{repo.name}")
                yield loop.create_task(cr.delete_repo(repo_name=repo.name, namespace=repo.namespace))

    for task in _it():
        await task


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


def read_file(path: str):
    with open(path, 'rt') as f:
        return f.read()


def cr_image_name(cr_region: str, cr_namespace: str, image: str):
    return f'registry.{cr_region}.aliyuncs.com/{cr_namespace}/{cr_repo_name(image)}:{cr_tag_name(image)}'


def cr_tag_name(image: str):
    s = image.split(':')[1]
    return s


def cr_info(image: str):
    tag = cr_tag_name(image)
    repo_name = cr_repo_name(image)
    return tag, repo_name


def cr_repo_name(image: str):
    s = image.split(':')[0]
    s = s.replace("/", "_")
    s = s.replace("\\", "_")
    return s


if __name__ == '__main__':
    cli(auto_envvar_prefix='MIRROR_OP')
