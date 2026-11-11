from decimal import Decimal
from typing import List, Optional
import datetime
from pydantic import BaseModel, Field, ConfigDict

# User Schemas
class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = "buyer"
    phone: Optional[str] = None
    delivery_city: Optional[str] = "Москва"

class UserOut(UserBase):
    id: int
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

# Product Variant Schemas
class ProductVariantOut(BaseModel):
    id: int
    size: str
    color: str
    cny_price: Decimal
    stock_status: str
    model_config = ConfigDict(from_attributes=True)

class ProductVariantCreate(BaseModel):
    size: str
    color: str = "Default"
    cny_price: Decimal
    stock_status: str = "to_order"

# Product Schemas
class ProductOut(BaseModel):
    id: int
    title: str
    brand: str
    category: str
    description: Optional[str] = None
    source: str
    base_cny_price: Decimal
    old_price_rub: Optional[Decimal] = None
    discount_percent: Optional[int] = None
    estimated_weight_kg: Decimal
    image_url: str
    badge_text: str
    is_active: bool
    is_popular: bool
    is_demo: bool
    variants: List[ProductVariantOut] = []
    model_config = ConfigDict(from_attributes=True)

class ProductCreate(BaseModel):
    title: str
    brand: str
    category: str
    description: Optional[str] = None
    source: str = "POIZON"
    base_cny_price: Decimal
    old_price_rub: Optional[Decimal] = None
    discount_percent: Optional[int] = None
    estimated_weight_kg: Decimal = Decimal("1.20")
    image_url: str
    badge_text: str = "POIZON"
    is_active: bool = True
    is_popular: bool = False
    is_demo: Optional[bool] = None
    variants: List[ProductVariantCreate] = []

# Banner Schemas
class BannerOut(BaseModel):
    id: int
    title: str
    subtitle: Optional[str] = None
    badge_text: str
    image_url: str
    link_url: str
    is_active: bool
    order_index: int
    model_config = ConfigDict(from_attributes=True)

# Settings Schemas
class StoreSettingsOut(BaseModel):
    exchange_rate: Decimal
    exchange_rate_updated_at: datetime.datetime
    exchange_rate_updated_by: str
    shipping_rub_per_kg: Decimal
    shipping_min_weight_kg: Decimal
    shipping_provider_name: str
    shipping_calc_url: str
    commission_type: str
    commission_value: Decimal
    commission_fixed_bonus: Decimal
    russia_shipping_type: str
    russia_shipping_cost: Decimal
    payment_bank_name: str
    payment_phone: str
    payment_card_number: str
    payment_recipient_name: str
    payment_instructions: str
    payment_is_configured: bool
    support_telegram_username: str
    model_config = ConfigDict(from_attributes=True)

class ExchangeRateUpdate(BaseModel):
    exchange_rate: Decimal = Field(..., gt=0, description="New CNY exchange rate")
    notes: Optional[str] = None

class ShippingSettingsUpdate(BaseModel):
    shipping_rub_per_kg: Decimal = Field(..., gt=0)
    shipping_min_weight_kg: Decimal = Field(..., ge=0)

class CommissionSettingsUpdate(BaseModel):
    commission_type: str = Field(..., pattern=r"^(percent|fixed|combo)$")
    commission_value: Decimal = Field(..., ge=0)
    commission_fixed_bonus: Optional[Decimal] = Decimal("0.00")

class RussiaShippingSettingsUpdate(BaseModel):
    russia_shipping_type: str = Field(..., pattern=r"^(fixed|by_city|unknown)$")
    russia_shipping_cost: Decimal = Field(..., ge=0)

class PaymentSettingsUpdate(BaseModel):
    payment_bank_name: str
    payment_phone: str
    payment_card_number: str
    payment_recipient_name: str
    payment_instructions: str
    support_telegram_username: Optional[str] = Field(default=None, pattern=r"^(?:[A-Za-z0-9_]{5,32})?$")
    payment_is_configured: bool = True

# Cart Schemas
class CartItemAdd(BaseModel):
    product_id: int = Field(gt=0)
    variant_id: Optional[int] = Field(None, gt=0)
    size: str = Field(min_length=1, max_length=50)
    color: str = "Default"
    quantity: int = Field(1, ge=1, le=10)

class CartItemOut(BaseModel):
    id: int
    product_id: int
    variant_id: Optional[int]
    size: str
    color: str
    quantity: int
    product: ProductOut
    model_config = ConfigDict(from_attributes=True)

# Order Schemas
class OrderItemOut(BaseModel):
    id: int
    product_id: Optional[int]
    title: str
    brand: str
    category: str
    size: str
    color: str
    quantity: int
    cny_price: Decimal
    rub_price: Decimal
    image_url: str
    product_link: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class PaymentProofOut(BaseModel):
    id: int
    amount_rub: Decimal
    payment_type: str
    receipt_filename: str
    receipt_image_url: str
    status: str
    admin_comment: Optional[str] = None
    submitted_at: datetime.datetime
    reviewed_at: Optional[datetime.datetime] = None
    reviewed_by: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class OrderStatusHistoryOut(BaseModel):
    id: int
    from_status: Optional[str]
    to_status: str
    comment: Optional[str]
    changed_by: str
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

class OrderOut(BaseModel):
    id: int
    order_number: str
    status: str
    status_label_ru: str
    delivery_city: str
    delivery_address: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = None
    customer_telegram: Optional[str] = None
    customer_notes: Optional[str] = None
    admin_notes: Optional[str] = None

    # Financial snapshots
    item_cny_price: Decimal
    exchange_rate_snapshot: Decimal
    item_rub_price: Decimal
    estimated_weight_kg: Decimal
    actual_weight_kg: Optional[Decimal] = None
    chargeable_weight_kg: Decimal
    intl_delivery_rate_rub: Decimal
    intl_delivery_cost_rub: Decimal
    russia_delivery_cost_rub: Decimal
    is_russia_delivery_known: bool
    commission_cost_rub: Decimal
    commission_description: str
    buyout_total_rub: Decimal
    grand_total_rub: Decimal
    paid_amount_rub: Decimal
    is_buyout_paid: bool
    is_fully_paid: bool

    promo_code: Optional[str] = None
    promo_discount_rub: Decimal = Decimal("0.00")

    shipping_carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    shipped_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    items: List[OrderItemOut] = []
    payment_proofs: List[PaymentProofOut] = []
    status_history: List[OrderStatusHistoryOut] = []
    model_config = ConfigDict(from_attributes=True)

class OrderContact(BaseModel):
    delivery_city: str = "Москва"
    delivery_address: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = None
    customer_telegram: Optional[str] = None
    customer_notes: Optional[str] = None
    promo_code: Optional[str] = None
    expected_total_rub: Optional[Decimal] = None


class OrderCreateRequest(OrderContact):
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    custom_product_title: Optional[str] = None
    custom_product_link: Optional[str] = None
    size: str
    color: Optional[str] = "Default"
    quantity: int = Field(1, ge=1)
    cny_price: Optional[Decimal] = None
    weight_kg: Optional[Decimal] = None


class CartSelectionItem(BaseModel):
    id: int = Field(gt=0)
    quantity: int = Field(ge=1)


class CartQuoteRequest(BaseModel):
    items: List[CartSelectionItem] = Field(min_length=1, max_length=150)
    delivery_city: str = "Москва"


class CartOrderRequest(CartQuoteRequest, OrderContact):
    expected_total_rub: Decimal = Field(ge=0)

# Promo Code Schemas
class PromoCodeOut(BaseModel):
    id: int
    code: str
    description: Optional[str] = None
    discount_type: str
    discount_value: Decimal
    min_order_rub: Decimal
    is_active: bool
    used_count: int
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

class PromoCodeCreate(BaseModel):
    code: str
    description: Optional[str] = None
    discount_type: str = "rub"  # 'rub' or 'percent'
    discount_value: Decimal
    min_order_rub: Decimal = Decimal("0.00")
    is_active: bool = True

class PromoCodeValidateRequest(BaseModel):
    code: str
    order_total_rub: Decimal

class PromoCodeValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_rub: Decimal
    message: str
    final_total_rub: Decimal

# Custom Buyout Schemas
class CustomBuyoutCreate(BaseModel):
    link_or_title: str
    size: Optional[str] = None
    cny_price: Optional[Decimal] = None
    image_url: Optional[str] = None
    notes: Optional[str] = None
    customer_name: Optional[str] = None
    customer_telegram: Optional[str] = None

class CustomBuyoutOut(BaseModel):
    id: int
    user_id: int
    customer_name: str
    customer_telegram: Optional[str] = None
    link_or_title: str
    size: Optional[str] = None
    cny_price: Optional[Decimal] = None
    image_url: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)

# Admin Dashboard
class AdminDashboardOut(BaseModel):
    total_orders: int
    total_revenue_rub: Decimal
    in_progress_count: int
    delivered_count: int
    current_exchange_rate: Decimal
    shipping_rate_per_kg: Decimal
    new_orders_count: int
    awaiting_payment_count: int
