from __future__ import annotations

import csv
from pathlib import Path

import pytest

from retail_agent.cli import AppContext
from retail_agent.config import Settings
from retail_agent.db.bootstrap import bootstrap_database
from retail_agent.db.connection import get_connection
from retail_agent.db.repositories import (
    CatalogRepository,
    CustomerRepository,
    InventoryRepository,
    OrderRepository,
    PromotionRepository,
    PurchaseOrderRepository,
    ReturnRepository,
    SupplierRepository,
)
from retail_agent.services.inventory_service import InventoryRepositories
from retail_agent.services.order_service import OrderRepositories
from retail_agent.services.procurement_service import ProcurementRepositories
from retail_agent.services.promotion_service import PromotionManagementRepositories
from retail_agent.services.reporting_service import ReportingRepositories
from retail_agent.services.returns_service import ReturnRepositories


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def seeded_db_path(tmp_path: Path) -> Path:
    return tmp_path / "store.db"


@pytest.fixture
def conn(seeded_db_path: Path):
    connection = get_connection(seeded_db_path)
    bootstrap_database(connection, DATA_DIR)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def settings(seeded_db_path: Path) -> Settings:
    return Settings(
        openai_api_key="test-key",
        model_name="gpt-5",
        db_path=seeded_db_path,
        seed_data_dir=DATA_DIR,
        log_level="INFO",
    )


@pytest.fixture
def app_context(conn, settings: Settings) -> AppContext:
    return AppContext(settings=settings, conn=conn)


@pytest.fixture
def catalog_repo(conn) -> CatalogRepository:
    return CatalogRepository(conn)


@pytest.fixture
def customer_repo(conn) -> CustomerRepository:
    return CustomerRepository(conn)


@pytest.fixture
def inventory_repo(conn) -> InventoryRepository:
    return InventoryRepository(conn)


@pytest.fixture
def order_repo(conn) -> OrderRepository:
    return OrderRepository(conn)


@pytest.fixture
def promotion_repo(conn) -> PromotionRepository:
    return PromotionRepository(conn)


@pytest.fixture
def purchase_order_repo(conn) -> PurchaseOrderRepository:
    return PurchaseOrderRepository(conn)


@pytest.fixture
def return_repo(conn) -> ReturnRepository:
    return ReturnRepository(conn)


@pytest.fixture
def supplier_repo(conn) -> SupplierRepository:
    return SupplierRepository(conn)


@pytest.fixture
def order_repos(
    catalog_repo: CatalogRepository,
    customer_repo: CustomerRepository,
    inventory_repo: InventoryRepository,
    order_repo: OrderRepository,
    promotion_repo: PromotionRepository,
) -> OrderRepositories:
    return OrderRepositories(
        catalog=catalog_repo,
        customers=customer_repo,
        inventory=inventory_repo,
        orders=order_repo,
        promotions=promotion_repo,
    )


@pytest.fixture
def return_repos(
    inventory_repo: InventoryRepository,
    order_repo: OrderRepository,
    return_repo: ReturnRepository,
) -> ReturnRepositories:
    return ReturnRepositories(
        inventory=inventory_repo,
        orders=order_repo,
        returns=return_repo,
    )


@pytest.fixture
def procurement_repos(
    catalog_repo: CatalogRepository,
    inventory_repo: InventoryRepository,
    purchase_order_repo: PurchaseOrderRepository,
    supplier_repo: SupplierRepository,
) -> ProcurementRepositories:
    return ProcurementRepositories(
        catalog=catalog_repo,
        inventory=inventory_repo,
        purchase_orders=purchase_order_repo,
        suppliers=supplier_repo,
    )


@pytest.fixture
def reporting_repos(
    inventory_repo: InventoryRepository,
    order_repo: OrderRepository,
    return_repo: ReturnRepository,
    supplier_repo: SupplierRepository,
) -> ReportingRepositories:
    return ReportingRepositories(
        inventory=inventory_repo,
        orders=order_repo,
        returns=return_repo,
        suppliers=supplier_repo,
    )


@pytest.fixture
def inventory_repos(
    inventory_repo: InventoryRepository,
    order_repo: OrderRepository,
) -> InventoryRepositories:
    return InventoryRepositories(inventory=inventory_repo, orders=order_repo)


@pytest.fixture
def promotion_management_repos(
    catalog_repo: CatalogRepository,
    promotion_repo: PromotionRepository,
) -> PromotionManagementRepositories:
    return PromotionManagementRepositories(
        catalog=catalog_repo,
        promotions=promotion_repo,
    )


def csv_row_count(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return max(sum(1 for _ in csv.DictReader(handle)), 0)

