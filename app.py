import logging
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///./shop_manager.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ProductDB(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    buying_price = Column(Float, nullable=False)
    selling_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    low_stock_threshold = Column(Integer, nullable=False)
    category = Column(String, default="General")

    sales = relationship("SaleDB", back_populates="product", cascade="all, delete-orphan")


class SaleDB(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    date = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)

    product = relationship("ProductDB", back_populates="sales")


class Product(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, 
        populate_by_name=True, 
        ser_by_alias=False,
        extra='ignore'  # Ignore extra fields like isDeleted from Flutter
    )
    
    id: str
    name: str
    buyingPrice: float = Field(..., gt=0, alias='buying_price')
    sellingPrice: float = Field(..., gt=0, alias='selling_price')
    quantity: int = Field(..., ge=0)
    lowStockThreshold: int = Field(..., ge=0, alias='low_stock_threshold')
    category: str = "General"


class Sale(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, ser_by_alias=False)
    
    productId: str = Field(alias='product_id')
    date: int
    quantity: int = Field(..., ge=1)


def create_database() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_product(db: Session, product_id: str) -> Optional[ProductDB]:
    return db.query(ProductDB).filter(ProductDB.id == product_id).first()


def create_or_update_product(db: Session, product: Product) -> ProductDB:
    existing = get_product(db, product.id)
    if existing:
        existing.name = product.name
        existing.buying_price = product.buyingPrice
        existing.selling_price = product.sellingPrice
        existing.quantity = product.quantity
        existing.low_stock_threshold = product.lowStockThreshold
        existing.category = product.category
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    db_product = ProductDB(
        id=product.id,
        name=product.name,
        buying_price=product.buyingPrice,
        selling_price=product.sellingPrice,
        quantity=product.quantity,
        low_stock_threshold=product.lowStockThreshold,
        category=product.category,
    )
    db.add(db_product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    db.refresh(db_product)
    return db_product


def get_products(db: Session) -> List[ProductDB]:
    return db.query(ProductDB).order_by(ProductDB.name).all()


def get_sales(db: Session) -> List[SaleDB]:
    return db.query(SaleDB).order_by(SaleDB.date).all()


def record_sale(db: Session, sale: Sale) -> SaleDB:
    product = get_product(db, sale.productId)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if sale.quantity > product.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock")

    product.quantity -= sale.quantity
    db_sale = SaleDB(
        product_id=sale.productId,
        date=sale.date,
        quantity=sale.quantity,
    )
    db.add(db_sale)
    db.add(product)
    db.commit()
    db.refresh(db_sale)
    return db_sale


def format_day_timestamp(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")


app = FastAPI(title="Shop Manager API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    create_database()


@app.get("/products", response_model=List[Product])
def list_products(db: Session = Depends(get_db)):
    return get_products(db)


@app.post("/products", response_model=Product)
def add_product(product: Product, db: Session = Depends(get_db)):
    logger.info(f"📦 Received POST /products request: {product.model_dump()}")
    try:
        result = create_or_update_product(db, product)
        logger.info(f"✅ Product saved successfully: {product.id}")
        return result
    except Exception as e:
        logger.error(f"❌ Error saving product: {type(e).__name__}: {str(e)}")
        raise


@app.put("/products/{product_id}", response_model=Product)
def update_product(product_id: str, product: Product, db: Session = Depends(get_db)):
    if product_id != product.id:
        raise HTTPException(status_code=400, detail="Product ID mismatch")
    if get_product(db, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return create_or_update_product(db, product)


@app.get("/sales", response_model=List[Sale])
def list_sales(db: Session = Depends(get_db)):
    return get_sales(db)


@app.post("/sales", response_model=Sale)
def add_sale(sale: Sale, db: Session = Depends(get_db)):
    return record_sale(db, sale)


@app.get("/reports/daily")
def daily_report(days: int = Query(7, ge=1), db: Session = Depends(get_db)):
    cutoff = datetime.now().timestamp() * 1000 - (days - 1) * 24 * 60 * 60 * 1000
    sales = (
        db.query(SaleDB)
        .filter(SaleDB.date >= cutoff)
        .order_by(SaleDB.date)
        .all()
    )
    result = {}
    for sale in sales:
        key = format_day_timestamp(sale.date)
        if key not in result:
            result[key] = {"sales": 0, "profit": 0, "date": sale.date}
        result[key]["sales"] += sale.quantity * sale.product.selling_price
        result[key]["profit"] += sale.quantity * (sale.product.selling_price - sale.product.buying_price)
    return {"dailyReports": sorted(result.values(), key=lambda x: x["date"])}
