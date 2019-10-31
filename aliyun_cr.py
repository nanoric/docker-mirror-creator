#!/usr/bin/env python
# coding=utf-8
import json
import logging
from asyncio import get_event_loop
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import RoaRequest
from aliyunsdkcr.request.v20160607 import (CreateRepoBuildRuleRequest, CreateRepoRequest,
                                           DeleteRepoRequest, GetRepoBuildListRequest,
                                           GetRepoBuildRuleListRequest, GetRepoListRequest,
                                           GetRepoTagsRequest,
                                           StartRepoBuildByRuleRequest, UpdateRepoBuildRuleRequest)

logger = logging.getLogger(__file__)


class BuildStatus(Enum):
    PENDING = auto()
    SUCCESS = auto()
    FAILED = auto()
    BUILDING = auto()


@dataclass()
class BuildInfo:
    id: str
    status: BuildStatus
    tag: str


@dataclass()
class Repository:
    name: str
    namespace: str
    id: int = 0


@dataclass()
class BuildRule:
    id: int
    tag: str
    dockerfile_dir: str
    dockerfile_name: str = 'Dockerfile'


class Request:

    def __init__(self, request_class, region: str, api: AcsClient):
        self.request: RoaRequest = request_class()
        # self.request.set_protocol_type('https')
        self.request.set_content_type("application/json")
        self.request.set_endpoint(f"cr.{region}.aliyuncs.com")
        self.api: AcsClient = api

        self.data = {}
        self.path_param = {}

    async def invoke(self) -> dict:
        for k, v in self.path_param.items():
            self.request.add_path_param(k, v)
        self.request.set_content(json.dumps(self.data))

        res = await get_event_loop().run_in_executor(
            None,
            self.api.do_action_with_exception,
            self.request,
        )

        return json.loads(res, encoding="GBK")


class AliyunCR:

    def __init__(
        self,
        access_key: str,
        access_secret: str,
        namespace: str = None,
        region: str = "cn-shanghai",
    ):
        self.region = region
        self.namespace = namespace
        self.api = AcsClient(access_key, access_secret, region)

    def _request(self, module: Any):
        request_name = module.__name__.split(".")[-1]
        request_class = getattr(module, request_name)
        return Request(request_class, region=self.region, api=self.api)

    async def create_build_rule(self,
                                repo_name: str,
                                dockerfile_dir: str,
                                tag: str,
                                force: bool = True,
                                ):
        """
        :param repo_name:
        :param dockerfile_dir:
        :param tag:
        :param force: if this is true and number of rules achieve the limit, delete one(first one).
        :return:
        """
        request = self._request(CreateRepoBuildRuleRequest)
        request.path_param = {
            "RepoNamespace": self.namespace,
            "RepoName": repo_name,
        }
        request.data = {
            "BuildRule": {
                "PushType": "GIT_BRANCH",
                "PushName": "master",
                "DockerfileLocation": dockerfile_dir,
                "DockerfileName": "Dockerfile",
                "ImageTag": tag,
                "Tag": tag,
            }
        }
        try:
            res = await request.invoke()
            return res['data']['buildRuleId']
        except Exception as e:
            limit = 5
            rules = [i async for i in self.list_build_rule(repo_name=repo_name)]
            if len(rules) >= limit:
                rule = rules[0]
                logger.warning(f"Rule limit exceed, editing a existing one:{rule.id}.")
                await self.edit_build_rule(repo_name=repo_name,
                                           rule_id=str(rule.id),
                                           dockerfile_dir=dockerfile_dir,
                                           tag=tag,
                                           )
                return rule.id
            else:
                raise e
            pass

    async def edit_build_rule(self, repo_name: str, rule_id: str, dockerfile_dir: str, tag: str):
        request = self._request(UpdateRepoBuildRuleRequest)
        request.path_param = {
            "RepoNamespace": self.namespace,
            "RepoName": repo_name,
            "BuildRuleId": str(rule_id),
        }
        request.data = {
            "BuildRule": {
                "PushType": "GIT_BRANCH",
                "PushName": "master",
                "DockerfileLocation": dockerfile_dir,
                "DockerfileName": "Dockerfile",
                "ImageTag": tag,
                "Tag": tag,
            }
        }
        return await request.invoke()

    async def build_by_rule(self, repo_name: str, rule_id: str):
        request = self._request(StartRepoBuildByRuleRequest)
        request.path_param = {
            "BuildRuleId": str(rule_id),
            "RepoNamespace": self.namespace,
            "RepoName": repo_name,
        }
        return await request.invoke()

    async def list_build_rule(self, repo_name: str):
        request = self._request(GetRepoBuildRuleListRequest)
        request.path_param = {
            "RepoNamespace": self.namespace,
            "RepoName": repo_name,
        }
        body = await request.invoke()
        data = body['data']
        rules = data['buildRules']
        for r in rules:
            yield BuildRule(
                id=r['buildRuleId'],
                tag=r['imageTag'],
                dockerfile_dir=r['dockerfileLocation'],
            )

    async def list_tags(self, repo_name: str):
        request = self._request(GetRepoTagsRequest)
        request.path_param = {
            "RepoNamespace": self.namespace,
            "RepoName": repo_name,
        }
        body = await request.invoke()
        data = body['data']
        tags = data['tags']
        for t in tags:
            yield t['tag']

    async def list_builds(self, repo_name: str, namespace: str = None):
        if namespace is None:
            namespace = self.namespace
        request = self._request(GetRepoBuildListRequest)
        request.path_param = {
            "RepoNamespace": namespace,
            "RepoName": repo_name,
        }
        body = await request.invoke()
        data = body['data']
        builds = data['builds']
        for b in builds:
            yield BuildInfo(
                id=b['buildId'],
                status=BuildStatus[b['buildStatus']],
                tag=b['image']['tag']
            )

    async def list_not_finished_builds(self, repo_name: str, tag: str, namespace: str = None):
        """
        list all builds that is under building or pending status.
        """
        builds = [b async for b in self.list_builds(repo_name=repo_name, namespace=namespace)]
        for b in builds:
            if b.tag == tag:
                if b.status == BuildStatus.PENDING or b.status == BuildStatus.BUILDING:
                    yield b

    async def list_repo(self, page: int = 0, page_size: int = 5000):
        request = self._request(GetRepoListRequest)
        request.path_param = {
            "Page": str(page),
            "PageSize": str(page_size),
        }
        res = await request.invoke()

        data: dict = res['data']
        repos: list = data['repos']
        for r in repos:
            yield Repository(
                id=r["repoId"],
                name=r["repoName"],
                namespace=r["repoNamespace"],
            )

    async def delete_repo(self, repo_name: str, namespace: str = None):
        if namespace is None:
            namespace = self.namespace
        request = self._request(DeleteRepoRequest)
        request.path_param = {
            "RepoNamespace": namespace,
            "RepoName": repo_name,
        }
        return await request.invoke()

    async def create_repo(self,
                          name: str,
                          github_namespace: str,
                          github_repo: str,
                          namespace: str = None,
                          public: bool = True,
                          ):
        if namespace is None:
            namespace = self.namespace
        request = self._request(CreateRepoRequest)
        request.data = {
            "Repo": {
                "Region": "cn-shanghai",
                "RepoName": name,
                "RepoType": "PUBLIC" if public else "PRIVATE",
                "Summary": "automatically created by docker-mirror-creator.",
                "RepoNamespaceName": namespace,
                "RepoNamespace": namespace,
                "RepoBuildType": "AUTO_BUILD",
            },
            "RepoSource": {
                "Source": {
                    "SourceRepoType": "GITHUB",
                    "SourceRepoNamespace": github_namespace,
                    "SourceRepoName": github_repo,
                },
                "BuildConfig": {
                    "IsAutoBuild": True,
                    "IsOversea": True,
                    "IsDisableCache": False
                }
            }
        }
        return await request.invoke()
