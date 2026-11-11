import asyncio
import datetime
from decimal import Decimal
from sqlalchemy import select
from apps.api.database import AsyncSessionLocal, engine, Base
from apps.api.models import (
    StoreSettings, Banner, Product, ProductVariant,
    User, Order, OrderItem, PaymentProof, OrderStatusHistory, PromoCode
)

CAMPAIGN_BANNERS = (
    dict(title="Скидка 5%", subtitle="При заказе от 15 000 ₽", badge_text="Код GRMV5",
         image_url="/banners/banner-grmv5.jpg", link_url="/catalog", order_index=2, is_active=True),
    dict(title="Выкуп по ссылке", subtitle="Пришлите ссылку с POIZON", badge_text="Отправить ссылку",
         image_url="/banners/banner-link-buyout.jpg", link_url="/?buyout=1", order_index=3, is_active=True),
)
CAMPAIGN_PROMO = dict(code="GRMV5", description="Скидка 5% при заказе от 15 000 ₽",
                      discount_type="percent", discount_value=Decimal("5.00"),
                      min_order_rub=Decimal("15000.00"), is_active=True, usage_limit=0)

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

async def seed_data():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # 1. Check if already seeded
        res = await session.execute(select(StoreSettings))
        settings_exist = res.scalar_one_or_none()

        if not settings_exist:
            print("Seeding StoreSettings...")
            store_settings = StoreSettings(
                exchange_rate=Decimal("12.80"),
                exchange_rate_updated_at=utcnow(),
                exchange_rate_updated_by="Администратор",
                shipping_rub_per_kg=Decimal("680.00"),
                shipping_min_weight_kg=Decimal("0.30"),
                shipping_provider_name="GRMV xLUCH store",
                shipping_calc_url="",
                commission_type="fixed",
                commission_value=Decimal("1000.00"),
                russia_shipping_type="unknown",
                russia_shipping_cost=Decimal("350.00"),
                payment_bank_name="Тестовый банк",
                payment_recipient_name="Тестовый получатель",
                payment_instructions="Демонстрационный заказ. Переводить деньги не нужно.",
                payment_is_configured=True,
                support_telegram_username="grmv_luch_support"
            )
            session.add(store_settings)

            # 2. Banners
            print("Seeding Banners...")
            banner1 = Banner(
                title="11.11 ГЛОБАЛЬНАЯ РАСПРОДАЖА",
                subtitle="Скидки до -58% на избранные позиции POIZON",
                badge_text="11.11",
                image_url="/banners/banner_1111.png",
                link_url="/catalog",
                is_active=True,
                order_index=1
            )
            session.add(banner1)
            session.add_all(Banner(**data) for data in CAMPAIGN_BANNERS)

            # 3. Users (Admin + Demo buyers)
            print("Seeding Users...")
            admin_user = User(
                telegram_id=123456789,
                username="admin_luch",
                first_name="Администратор",
                last_name="Store",
                role="admin",
                phone="+7 (968) 060-22-10",
                delivery_city="Москва"
            )
            session.add(admin_user)

            buyer1 = User(
                telegram_id=1110001,
                username="ivan_p",
                first_name="Иван",
                last_name="П.",
                role="buyer",
                phone="+7 (968) 060-22-10",
                delivery_city="Москва"
            )
            session.add(buyer1)

            # 4. Products & Variants (matching Reference 01 Popular cards)
            print("Seeding Products...")
            p1 = Product(
                title="Nike Air Max 90",
                brand="Nike",
                category="Кроссовки",
                description="Культовые кроссовки Nike Air Max 90 в классической белой расцветке с черным свушем и серыми акцентами. Легендарная воздушная подушка Max Air в области пятки и вафельная подошва.",
                source="POIZON",
                base_cny_price=Decimal("580.00"),
                old_price_rub=Decimal("14490.00"),
                discount_percent=37,
                estimated_weight_kg=Decimal("1.30"),
                image_url="/products/prod_air_max_90_white.png",
                badge_text="POIZON",
                is_active=True,
                is_popular=True,
                is_demo=False
            )
            session.add(p1)
            await session.flush()

            for s in ["38", "39", "40", "41", "42", "42.5", "43", "44", "45", "46"]:
                session.add(ProductVariant(
                    product_id=p1.id,
                    size=s,
                    color="White/Black",
                    cny_price=Decimal("580.00"),
                    stock_status="to_order"
                ))

            p2 = Product(
                title="adidas Samba OG",
                brand="adidas",
                category="Кроссовки",
                description="Культовый силуэт adidas Samba OG из мягкой зернистой черной кожи с замшевым Т-образным носком, тремя белыми полосками и ретро-подошвой из резины gum sole.",
                source="POIZON",
                base_cny_price=Decimal("490.00"),
                old_price_rub=Decimal("10990.00"),
                discount_percent=32,
                estimated_weight_kg=Decimal("1.20"),
                image_url="/products/prod_samba_og_black.png",
                badge_text="POIZON",
                is_active=True,
                is_popular=True,
                is_demo=False
            )
            session.add(p2)
            await session.flush()

            for s in ["36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46"]:
                session.add(ProductVariant(
                    product_id=p2.id,
                    size=s,
                    color="Black/Gum",
                    cny_price=Decimal("490.00"),
                    stock_status="to_order"
                ))

            p3 = Product(
                title="Nike Air Max 90 «Light Bone»",
                brand="Nike",
                category="Кроссовки",
                description="Премиальная версия Nike Air Max 90 в палитре White / Light Bone / Dark Brown. Натуральная замша, дышащий текстиль и комфортная амортизация Air.",
                source="POIZON",
                base_cny_price=Decimal("520.00"),
                old_price_rub=Decimal("13490.00"),
                discount_percent=41,
                estimated_weight_kg=Decimal("1.30"),
                image_url="/products/prod_air_max_90_brown.png",
                badge_text="POIZON",
                is_active=True,
                is_popular=True,
                is_demo=False
            )
            session.add(p3)
            await session.flush()

            for s in ["38", "39", "40", "41", "42", "42.5", "43", "44", "45", "46"]:
                session.add(ProductVariant(
                    product_id=p3.id,
                    size=s,
                    color="White/Brown",
                    cny_price=Decimal("520.00"),
                    stock_status="to_order"
                ))

            p4 = Product(
                title="Худи Nike Club Fleece Grey",
                brand="Nike",
                category="Одежда",
                description="Классическая толстовка с капюшоном из плотного хлопка с флисовым начесом Club Fleece. Вышитый белый логотип Nike Futura на груди, карман-кенгуру.",
                source="POIZON",
                base_cny_price=Decimal("380.00"),
                old_price_rub=Decimal("8990.00"),
                discount_percent=28,
                estimated_weight_kg=Decimal("1.50"),
                image_url="/products/prod_nike_hoodie_grey.png",
                badge_text="POIZON",
                is_active=True,
                is_popular=True,
                is_demo=False
            )
            session.add(p4)
            await session.flush()

            for s in ["S", "M", "L", "XL", "XXL"]:
                session.add(ProductVariant(
                    product_id=p4.id,
                    size=s,
                    color="Grey Heather",
                    cny_price=Decimal("380.00"),
                    stock_status="to_order"
                ))

            p5 = Product(
                title="Nike Mercurial Superfly 11 Pro",
                brand="Nike",
                category="Кроссовки",
                description="Профессиональные футбольные бутсы для игры на натуральных и синтетических покрытиях. Легкий верх Flyknit и подошва с шипами для взрывного ускорения.",
                source="POIZON",
                base_cny_price=Decimal("990.00"),
                old_price_rub=Decimal("15990.00"),
                discount_percent=40,
                estimated_weight_kg=Decimal("1.30"),
                image_url="/products/mercurial_superfly_card.png",
                badge_text="POIZON",
                is_active=True,
                is_popular=True,
                is_demo=False
            )
            session.add(p5)
            await session.flush()

            for s in ["40", "41", "42", "42.5", "43", "44"]:
                session.add(ProductVariant(
                    product_id=p5.id,
                    size=s,
                    color="Pink",
                    cny_price=Decimal("990.00"),
                    stock_status="to_order"
                ))

            p6 = Product(
                title="Nike Air Max 90 «Hypervenom»",
                brand="Nike",
                category="Кроссовки",
                description="Лимитированное издание в яркой оранжево-черной расцветке Hypervenom с черным матовым свушем и контрастной подошвой.",
                source="POIZON",
                base_cny_price=Decimal("550.00"),
                old_price_rub=Decimal("14490.00"),
                discount_percent=35,
                estimated_weight_kg=Decimal("1.30"),
                image_url="/products/nike_hypervenom_orange.png",
                badge_text="POIZON",
                is_active=True,
                is_popular=True,
                is_demo=False
            )
            session.add(p6)
            await session.flush()

            for s in ["40", "41", "42", "42.5", "43", "44", "45"]:
                session.add(ProductVariant(
                    product_id=p6.id,
                    size=s,
                    color="Orange/Black",
                    cny_price=Decimal("550.00"),
                    stock_status="to_order"
                ))

            # 5. Seed Demo Orders matching Reference 03 and Reference 04
            print("Seeding Orders...")
            demo_orders_spec = [
                ("#4587", "Nike Mercurial Superfly 11 Pro", "42", "ivan_aa", "7680.00", "new", "Новый", "07.11.2026 19:24", "/products/thumb_mercurial_pink.png"),
                ("#4586", "Nike Air Max 90 Hypervenom", "43", "k_kirill", "8320.00", "awaiting_payment", "Ожидает оплаты", "07.11.2026 18:47", "/products/thumb_hypervenom_orange.png"),
                ("#4585", "Nike Air Max 90 Mercurial", "42", "sasha_m", "7900.00", "paid", "Оплачен", "07.11.2026 17:36", "/products/thumb_mercurial_yellow.png"),
                ("#4584", "DCSHOES KRYSSA EDGE", "42", "dmitry_p", "6500.00", "purchased", "Выкуплен", "07.11.2026 15:20", "/products/thumb_dcshoes_sand.png"),
                ("#4583", "Nike Mercurial Superfly 11 Pro", "41", "alina_v", "7680.00", "china_warehouse", "На складе в Китае", "06.11.2026 22:11", "/products/thumb_mercurial_pink.png"),
                ("#4582", "Nike Air Max 90 Mercurial", "43", "ruslan_77", "7900.00", "shipped", "Отправлен", "05.11.2026 14:02", "/products/thumb_mercurial_yellow.png"),
                ("#4581", "Nike Air Max 90 Hypervenom", "42", "maxim_t", "8320.00", "delivered", "Доставлен", "03.11.2026 11:09", "/products/thumb_hypervenom_orange.png"),
            ]

            for o_num, title, size, buyer_tg, total_str, status_code, status_ru, date_str, img in demo_orders_spec:
                order = Order(
                    order_number=o_num,
                    user_id=buyer1.id,
                    status=status_code,
                    status_label_ru=status_ru,
                    delivery_city="Москва",
                    customer_name=buyer_tg,
                    customer_telegram=f"@{buyer_tg}",
                    customer_phone="+7 (999) 123-45-67",
                    item_cny_price=Decimal("600.00"),
                    exchange_rate_snapshot=Decimal("12.80"),
                    item_rub_price=Decimal(total_str) - Decimal("1000.00"),
                    estimated_weight_kg=Decimal("1.20"),
                    chargeable_weight_kg=Decimal("1.20"),
                    intl_delivery_rate_rub=Decimal("680.00"),
                    intl_delivery_cost_rub=Decimal("816.00"),
                    russia_delivery_cost_rub=Decimal("350.00"),
                    commission_cost_rub=Decimal("1000.00"),
                    buyout_total_rub=Decimal(total_str),
                    grand_total_rub=Decimal(total_str),
                    paid_amount_rub=Decimal(total_str) if status_code in ["paid", "purchased", "china_warehouse", "shipped", "delivered"] else Decimal("0.00"),
                    is_buyout_paid=status_code in ["paid", "purchased", "china_warehouse", "shipped", "delivered"],
                    is_fully_paid=status_code in ["paid", "purchased", "china_warehouse", "shipped", "delivered"],
                    tracking_number="RK982736154CN" if status_code in ["shipped", "delivered"] else None
                )
                session.add(order)
                await session.flush()

                item = OrderItem(
                    order_id=order.id,
                    product_id=p1.id,
                    title=title,
                    brand="Nike",
                    size=size,
                    quantity=1,
                    cny_price=Decimal("600.00"),
                    rub_price=Decimal(total_str),
                    image_url=img
                )
                session.add(item)

                hist = OrderStatusHistory(
                    order_id=order.id,
                    from_status=None,
                    to_status=status_code,
                    comment="Заказ создан и обработан",
                    changed_by="Администратор"
                )
                session.add(hist)

            # Order #1042 (Detailed match to Reference 04)
            order_1042 = Order(
                order_number="#1042",
                user_id=buyer1.id,
                status="new",
                status_label_ru="Новый",
                delivery_city="Москва",
                customer_name="Иван П.",
                customer_telegram="@ivan_p",
                customer_phone="+7 968 060-22-10",
                item_cny_price=Decimal("550.00"),
                exchange_rate_snapshot=Decimal("12.80"),
                item_rub_price=Decimal("7040.00"),
                estimated_weight_kg=Decimal("1.30"),
                chargeable_weight_kg=Decimal("1.30"),
                intl_delivery_rate_rub=Decimal("680.00"),
                intl_delivery_cost_rub=Decimal("884.00"),
                russia_delivery_cost_rub=Decimal("350.00"),
                commission_cost_rub=Decimal("704.00"),
                commission_description="Комиссия магазина (10%)",
                buyout_total_rub=Decimal("7744.00"),
                grand_total_rub=Decimal("8978.00"),
                paid_amount_rub=Decimal("0.00"),
                is_buyout_paid=False,
                is_fully_paid=False
            )
            session.add(order_1042)
            await session.flush()

            item_1042 = OrderItem(
                order_id=order_1042.id,
                product_id=p1.id,
                title="Nike Mercurial Superfly 11 Pro",
                brand="Nike",
                size="42",
                quantity=1,
                cny_price=Decimal("550.00"),
                rub_price=Decimal("7040.00"),
                image_url="/products/mercurial_superfly_card.png"
            )
            session.add(item_1042)

            # Payment receipt proof for #1042
            proof_1042 = PaymentProof(
                order_id=order_1042.id,
                user_id=buyer1.id,
                amount_rub=Decimal("8978.00"),
                payment_type="buyout",
                receipt_filename="photo_2026-11-07_12-17-04.jpg",
                receipt_image_url="/images/receipt_sample.png",
                status="submitted"
            )
            session.add(proof_1042)

            hist_1042 = OrderStatusHistory(
                order_id=order_1042.id,
                from_status=None,
                to_status="new",
                comment="Создана заявка, прикреплен чек об оплате",
                changed_by="Покупатель"
            )
            session.add(hist_1042)

            await session.commit()
            print("Successfully seeded all demo data!")
        # Seed PromoCodes if empty
        res_promo = await session.execute(select(PromoCode))
        if not res_promo.scalars().first():
            print("Seeding initial PromoCodes...")
            session.add(PromoCode(
                code="START",
                description="Скидка 500 ₽ на заказ от 5 000 ₽",
                discount_type="rub",
                discount_value=Decimal("500.00"),
                min_order_rub=Decimal("5000.00"),
                is_active=True
            ))
            session.add(PromoCode(
                code="LUCH1000",
                description="Скидка 1 000 ₽ на заказ от 15 000 ₽",
                discount_type="rub",
                discount_value=Decimal("1000.00"),
                min_order_rub=Decimal("15000.00"),
                is_active=True
            ))
            session.add(PromoCode(**CAMPAIGN_PROMO))
            await session.commit()
            print("Seeded PromoCodes successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
