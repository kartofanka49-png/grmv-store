import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select, update

from apps.api.database import AsyncSessionLocal
from apps.api.models import Product, ProductVariant

ROOT = Path(__file__).resolve().parents[2]


async def complete_preview_catalog(target=150):
    delivery_note = "Пример срока доставки: 10–18 дней. Данные для теста."
    async with AsyncSessionLocal() as session:
        boot = await session.scalar(select(Product).where(Product.image_url == "/products/mercurial_superfly_card.png",
                                                          Product.title == "Nike Mercurial Superfly 11 Pro"))
        if boot and boot.base_cny_price == Decimal("990"):
            boot.base_cny_price = Decimal("600")
            await session.execute(update(ProductVariant).where(ProductVariant.product_id == boot.id,
                                    ProductVariant.cny_price == Decimal("990")).values(cny_price=Decimal("600")))
        total = await session.scalar(select(func.count()).select_from(Product))
        if total >= target:
            await session.commit()
            return
        for product in (await session.scalars(select(Product))).all():
            product.is_demo = True
            if delivery_note not in (product.description or ""):
                product.description = "\n\n".join(filter(None, [product.description, delivery_note]))
        source = json.loads((ROOT / "data" / "demo_catalog.json").read_text())
        for row in source[:target - total]:
            price = Decimal(row["cny"])
            product = Product(
                title=row["title"], brand=row["brand"], category="Кроссовки" if row["category"] == "Обувь" else row["category"],
                description=row["description"] + "\n\n" + delivery_note, source="Демо", base_cny_price=price, is_demo=True,
                estimated_weight_kg=Decimal(row["grams"]) / 1000, image_url=row["image"].replace("/static/", "/"),
                badge_text="Демо", is_active=True, is_popular=False,
            )
            session.add(product)
            await session.flush()
            session.add_all(ProductVariant(product_id=product.id, size=size, color="", cny_price=price, stock_status="to_order")
                            for size in row["sizes"])
        await session.commit()
