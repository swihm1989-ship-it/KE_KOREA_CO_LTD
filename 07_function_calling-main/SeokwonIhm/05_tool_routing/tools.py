"""수업용 카탈로그와 구매 규정을 읽고 실제 단가로 견적을 계산한다."""
import csv
from pathlib import Path

from langchain_core.tools import tool

from contracts import FindProductsArgs, Policy, Product, ProductIdArgs, ProductList, Quote, QuoteArgs

DATA = Path(__file__).resolve().parent / "data"


def read_catalog() -> list[Product]:
    products = []
    with (DATA / "catalog.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            row["price_won"] = int(row["price_won"])
            row["stock"] = int(row["stock"])
            products.append(Product.model_validate(row))
    return products


def get_product(product_id: str) -> Product:
    product = next((item for item in read_catalog() if item.product_id == product_id), None)
    if product is None:
        raise ValueError("카탈로그에 없는 제품 ID입니다.")
    return product


@tool(args_schema=FindProductsArgs)
def find_products(max_price: int, category: str = "전체") -> ProductList:
    """개당 최대 예산으로 수업용 비품의 가격·재고를 조회한다. 예산이 없으면 질문한다. 종류 생략은 전체다."""
    return ProductList(products=[item for item in read_catalog()
                                if item.price_won <= max_price
                                and (category == "전체" or item.category == category)])


@tool(args_schema=ProductIdArgs)
def lookup_product(product_id: str) -> Product:
    """명시된 제품 ID의 가격·재고·설명을 조회한다. 예산이나 견적 수량은 필요하지 않다."""
    return get_product(product_id)


@tool
def read_purchase_policy() -> Policy:
    """사내 비품 구매 검토의 수량·예산·참고 문서 사용 기준을 읽는다. 가격·재고 조회에는 사용하지 않는다."""
    return Policy(text=(DATA / "purchase_policy.md").read_text(encoding="utf-8"))


@tool(args_schema=QuoteArgs)
def calculate_quote(product_id: str, quantity: int) -> Quote:
    """실제 카탈로그 단가와 수량으로 견적·재고 가능 여부를 계산한다. 주문·승인·저장은 하지 않는다."""
    product = get_product(product_id)
    return Quote(product_id=product.product_id, name=product.name, quantity=quantity,
                 unit_price_won=product.price_won, total_won=product.price_won * quantity,
                 stock=product.stock, available=product.stock >= quantity,
                 reference_url=product.reference_url)
