import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean,
    Numeric, DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from apps.api.database import Base

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    role = Column(String(50), default="buyer", nullable=False)  # 'buyer', 'admin'
    phone = Column(String(50), nullable=True)
    delivery_city = Column(String(100), default="Москва", nullable=True)
    delivery_address = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    cart_items = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")

class BotOptOut(Base):
    __tablename__ = "bot_opt_outs"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class BotBroadcast(Base):
    __tablename__ = "bot_broadcasts"

    id = Column(String(36), primary_key=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BotMessage(Base):
    __tablename__ = "bot_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "incoming_message_id"),
        Index("ix_bot_messages_status_id", "status", "id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broadcast_id = Column(String(36), ForeignKey("bot_broadcasts.id", ondelete="CASCADE"), nullable=True, index=True)
    incoming_message_id = Column(BigInteger, nullable=True)
    request_id = Column(String(36), nullable=True, unique=True)
    body = Column(Text, nullable=True)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class StoreSettings(Base):
    __tablename__ = "store_settings"

    id = Column(Integer, primary_key=True)
    # Exchange rate CNY -> RUB (ONLY manual)
    exchange_rate = Column(Numeric(10, 4), default=Decimal("12.80"), nullable=False)
    exchange_rate_updated_at = Column(DateTime(timezone=True), default=utcnow)
    exchange_rate_updated_by = Column(String(100), default="Admin")

    # RaketaCN delivery settings
    shipping_rub_per_kg = Column(Numeric(10, 2), default=Decimal("680.00"), nullable=False)
    shipping_min_weight_kg = Column(Numeric(10, 2), default=Decimal("0.30"), nullable=False)
    shipping_provider_name = Column(String(100), default="GRMV xLUCH store", nullable=False)
    shipping_calc_url = Column(String(255), default="")

    # Store commission
    commission_type = Column(String(50), default="percent", nullable=False)  # 'percent', 'fixed', 'combo'
    commission_value = Column(Numeric(10, 2), default=Decimal("10.00"), nullable=False) # 10% or 1000 RUB
    commission_fixed_bonus = Column(Numeric(10, 2), default=Decimal("0.00")) # for combo mode

    # Russia delivery
    russia_shipping_type = Column(String(50), default="fixed", nullable=False) # 'fixed', 'by_city', 'unknown'
    russia_shipping_cost = Column(Numeric(10, 2), default=Decimal("350.00"), nullable=False)

    # Payment requisites (for manual bank transfers)
    payment_bank_name = Column(String(100), default="")
    payment_phone = Column(String(50), default="")
    payment_card_number = Column(String(50), default="")
    payment_recipient_name = Column(String(255), default="")
    payment_instructions = Column(Text, default="")
    payment_is_configured = Column(Boolean, default=False)

    # Support contact
    support_telegram_username = Column(String(100), default="")
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ExchangeRateAudit(Base):
    __tablename__ = "exchange_rate_audits"

    id = Column(Integer, primary_key=True)
    old_rate = Column(Numeric(10, 4), nullable=False)
    new_rate = Column(Numeric(10, 4), nullable=False)
    changed_by = Column(String(100), default="Admin")
    changed_at = Column(DateTime(timezone=True), default=utcnow)
    notes = Column(String(255), nullable=True)

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    brand = Column(String(100), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)  # 'Кроссовки', 'Одежда', 'Аксессуары', 'Бутсы'
    description = Column(Text, nullable=True)
    source = Column(String(50), default="POIZON")  # 'POIZON', 'Taobao', '1688', 'Other'
    
    # Pricing & Weight
    base_cny_price = Column(Numeric(10, 2), nullable=False)
    old_price_rub = Column(Numeric(10, 2), nullable=True)  # Strikethrough price
    discount_percent = Column(Integer, nullable=True)     # e.g. 37 (-37%)
    estimated_weight_kg = Column(Numeric(10, 2), default=Decimal("1.20"), nullable=False)
    
    # Media
    image_url = Column(String(500), nullable=False)
    badge_text = Column(String(50), default="POIZON")

    is_active = Column(Boolean, default=True)
    is_popular = Column(Boolean, default=True)
    is_demo = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    cart_items = relationship("CartItem", back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    size = Column(String(50), nullable=False)      # e.g. '40', '41', '42', '42.5', 'L', etc.
    color = Column(String(50), default="Default")
    cny_price = Column(Numeric(10, 2), nullable=False)
    stock_status = Column(String(50), default="to_order")  # 'to_order', 'in_stock', 'out_of_stock'

    product = relationship("Product", back_populates="variants")

class Banner(Base):
    __tablename__ = "banners"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    badge_text = Column(String(50), default="11.11")
    image_url = Column(String(500), nullable=False)
    link_url = Column(String(255), default="/catalog")
    is_active = Column(Boolean, default=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    size = Column(String(50), nullable=False)
    color = Column(String(50), default="Default")
    quantity = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False) # e.g. #4587, #1042
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Status progression:
    # 'new' -> 'awaiting_quote_confirmation' -> 'awaiting_payment' -> 'payment_review' ->
    # 'paid' -> 'purchased' -> 'china_warehouse' -> 'shipped' -> 'delivered' | 'cancelled'
    status = Column(String(50), default="new", nullable=False, index=True)
    status_label_ru = Column(String(100), default="Новый", nullable=False)

    # Customer input
    delivery_city = Column(String(100), default="Москва", nullable=False)
    delivery_address = Column(String(255), nullable=True)
    customer_name = Column(String(255), nullable=False)
    customer_phone = Column(String(50), nullable=True)
    customer_telegram = Column(String(100), nullable=True)
    customer_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Financial Snapshot (NEVER mutated when store settings change!)
    item_cny_price = Column(Numeric(10, 2), nullable=False)
    exchange_rate_snapshot = Column(Numeric(10, 4), nullable=False)
    item_rub_price = Column(Numeric(10, 2), nullable=False)

    estimated_weight_kg = Column(Numeric(10, 2), default=Decimal("1.20"), nullable=False)
    actual_weight_kg = Column(Numeric(10, 2), nullable=True)
    chargeable_weight_kg = Column(Numeric(10, 2), default=Decimal("1.20"), nullable=False)

    intl_delivery_rate_rub = Column(Numeric(10, 2), default=Decimal("680.00"), nullable=False)
    intl_delivery_cost_rub = Column(Numeric(10, 2), default=Decimal("816.00"), nullable=False)

    russia_delivery_cost_rub = Column(Numeric(10, 2), default=Decimal("350.00"), nullable=False)
    is_russia_delivery_known = Column(Boolean, default=True)

    commission_cost_rub = Column(Numeric(10, 2), default=Decimal("1000.00"), nullable=False)
    commission_description = Column(String(100), default="Комиссия магазина")

    # Payment splits
    buyout_total_rub = Column(Numeric(10, 2), nullable=False)  # Initial payment
    grand_total_rub = Column(Numeric(10, 2), nullable=False)   # Total sum to pay
    paid_amount_rub = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    is_buyout_paid = Column(Boolean, default=False)
    is_fully_paid = Column(Boolean, default=False)

    # Promo code discount
    promo_code = Column(String(50), nullable=True)
    promo_discount_rub = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)

    # Shipping & Tracking
    shipping_carrier = Column(String(100), default="GRMV xLUCH store")
    tracking_number = Column(String(100), nullable=True)
    tracking_url = Column(String(500), nullable=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payment_proofs = relationship("PaymentProof", back_populates="order", cascade="all, delete-orphan")
    status_history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan")

class OrderDeletionWatermark(Base):
    __tablename__ = "order_deletion_watermark"

    id = Column(Integer, primary_key=True)
    last_deleted_id = Column(Integer, nullable=False)


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    brand = Column(String(100), default="POIZON")
    category = Column(String(100), default="Обувь")
    size = Column(String(50), nullable=False)
    color = Column(String(50), default="Default")
    quantity = Column(Integer, default=1, nullable=False)
    cny_price = Column(Numeric(10, 2), nullable=False)
    rub_price = Column(Numeric(10, 2), nullable=False)
    image_url = Column(String(500), nullable=False)
    product_link = Column(String(500), nullable=True)

    order = relationship("Order", back_populates="items")

class PaymentProof(Base):
    __tablename__ = "payment_proofs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount_rub = Column(Numeric(10, 2), nullable=False)
    payment_type = Column(String(50), default="buyout")  # 'buyout', 'shipping', 'full'
    receipt_filename = Column(String(255), nullable=False)
    receipt_image_url = Column(String(500), nullable=False)
    status = Column(String(50), default="submitted")  # 'submitted', 'approved', 'rejected'
    admin_comment = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=utcnow)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String(100), nullable=True)

    order = relationship("Order", back_populates="payment_proofs")

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    comment = Column(String(255), nullable=True)
    changed_by = Column(String(100), default="System")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    order = relationship("Order", back_populates="status_history")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(50), nullable=False)
    user_identifier = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class PromoCode(Base):
    __tablename__ = "promocodes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    discount_type = Column(String(20), default="rub", nullable=False)  # 'rub' or 'percent'
    discount_value = Column(Numeric(10, 2), nullable=False)           # 500.00 or 10.00 (%)
    min_order_rub = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    usage_limit = Column(Integer, default=1000)
    used_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class CustomBuyoutRequest(Base):
    __tablename__ = "custom_buyout_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    customer_name = Column(String(255), nullable=False)
    customer_telegram = Column(String(100), nullable=True)
    link_or_title = Column(String(500), nullable=False)
    size = Column(String(50), nullable=True)
    cny_price = Column(Numeric(10, 2), nullable=True)
    image_url = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(50), default="pending", nullable=False)  # 'pending', 'contacted', 'closed'
    created_at = Column(DateTime(timezone=True), default=utcnow)
