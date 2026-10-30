"""비품 조회·견적의 입력과 반환 구조를 정의한다."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Product(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    product_id: str
    name: str
    category: Literal["키보드", "마우스", "허브"]
    price_won: int = Field(ge=0)
    stock: int = Field(ge=0)
    description: str
    reference_url: str


class ProductList(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    products: list[Product]


class FindProductsArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    max_price: int = Field(ge=0)
    category: Literal["전체", "키보드", "마우스", "허브"] = "전체"


class QuoteArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    product_id: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=100)


class ProductIdArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    product_id: str = Field(min_length=1)


class Quote(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    product_id: str
    name: str
    quantity: int = Field(ge=1, le=100)
    unit_price_won: int = Field(ge=0)
    total_won: int = Field(ge=0)
    stock: int = Field(ge=0)
    available: bool
    reference_url: str


class Policy(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    text: str


class Route(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    route: Literal["catalog", "product", "quote", "policy", "clarify", "general", "unsupported"]
    max_price: int | None = Field(ge=0)
    category: Literal["전체", "키보드", "마우스", "허브"]
    product_id: str | None = Field(pattern=r"^P\d{3}$")
    quantity: int | None = Field(ge=1, le=100)
    reply: str

    @model_validator(mode="after")
    def check_route_fields(self):
        fields = {"max_price": self.max_price, "product_id": self.product_id, "quantity": self.quantity}
        required = {"catalog": {"max_price"}, "product": {"product_id"},
                    "quote": {"product_id", "quantity"}, "policy": set()}
        if self.route in required:
            needed = required[self.route]
            if any(fields[name] is None for name in needed):
                raise ValueError("선택한 로컬 경로의 필수 입력이 없습니다.")
            if any(value is not None for name, value in fields.items() if name not in needed):
                raise ValueError("선택한 경로에서 사용하지 않는 입력은 null이어야 합니다.")
            if self.reply != "":
                raise ValueError("로컬 실행 경로의 reply는 빈 문자열이어야 합니다.")
        else:
            if not self.reply.strip():
                raise ValueError("안내 경로에는 실제 안내가 필요합니다.")
            if self.route in {"general", "unsupported"} and any(value is not None for value in fields.values()):
                raise ValueError("일반 설명·지원 밖 안내에는 실행 인자를 넣지 않습니다.")
            if self.route == "clarify" and (self.max_price is not None or
                    (self.product_id is not None and self.quantity is not None)):
                raise ValueError("clarify에는 누락된 입력을 임의로 채우지 않습니다.")
        if self.route not in {"catalog", "clarify"} and self.category != "전체":
            raise ValueError("이 경로에서 사용하지 않는 category는 전체로 둡니다.")
        return self
