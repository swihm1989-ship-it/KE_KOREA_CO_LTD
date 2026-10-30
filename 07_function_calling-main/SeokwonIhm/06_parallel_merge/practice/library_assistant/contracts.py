"""도구 입력, JSON 자료와 병합 반환의 계약."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
BranchId = Literal['central', 'east', 'west']
Count = Annotated[int, Field(ge=0)]
Duration = Annotated[float, Field(ge=0, allow_inf_nan=False)]
BRANCHES = (('central', '중앙도서관'), ('east', '동부도서관'), ('west', '서부도서관'))


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class CompareArgs(Contract):
    title: Text


class Book(Contract):
    title: Text
    available_count: Count


class Catalog(Contract):
    branch_id: BranchId
    name: Text
    updated_at: Text
    books: list[Book]

    @model_validator(mode='after')
    def check_books(self):
        titles = [book.title for book in self.books]
        if len(titles) != len(set(titles)):
            raise ValueError('같은 지점에 중복된 도서명이 있습니다.')
        return self


class Scenario(Contract):
    delays: dict[BranchId, Duration]
    failures: list[BranchId]

    @model_validator(mode='after')
    def check_branches(self):
        if set(self.delays) != {branch_id for branch_id, _ in BRANCHES}:
            raise ValueError('세 지점 모두의 지연 조건이 필요합니다.')
        return self


class BranchResult(Contract):
    branch_id: BranchId
    name: Text
    title: Text
    found: bool
    available_count: Count | None
    updated_at: Text

    @model_validator(mode='after')
    def check_count(self):
        if self.found != (self.available_count is not None):
            raise ValueError('등록 도서는 정수 권수, 미등록 도서는 null이어야 합니다.')
        return self


class JobRecord(Contract):
    branch_id: BranchId
    name: Text
    status: Literal['ok', 'error']
    result: BranchResult | None
    error: Text | None
    started_at: Text
    finished_at: Text
    elapsed_seconds: Duration

    @model_validator(mode='after')
    def check_status(self):
        if self.status == 'ok':
            if self.result is None or self.error is not None:
                raise ValueError('성공 작업에는 조회 결과만 필요합니다.')
            if self.result.branch_id != self.branch_id or self.result.name != self.name:
                raise ValueError('작업 지점과 반환 지점이 다릅니다.')
        elif self.result is not None or self.error is None:
            raise ValueError('실패 작업에는 오류만 필요합니다.')
        return self


class BranchError(Contract):
    branch_id: BranchId
    name: Text
    error: Text


class MergedResult(Contract):
    title: Text
    collection_status: Literal['complete', 'partial', 'failed']
    available_branches: list[BranchResult]
    unavailable_branches: list[BranchResult]
    not_found_branches: list[BranchResult]
    errors: list[BranchError]
    jobs: list[JobRecord] = Field(min_length=3, max_length=3)
    elapsed_seconds: Duration
    peak_active: int = Field(ge=1, le=2)


def check_concurrency(value):
    if type(value) is not int or value not in (1, 2):
        raise ValueError('동시 실행 상한은 정수 1 또는 2여야 합니다.')
    return value
