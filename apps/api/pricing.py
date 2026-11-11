from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from pydantic import BaseModel, Field

def round_money(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def round_rub_int(val: Decimal) -> int:
    return int(val.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

class PricingRequest(BaseModel):
    cny_price: Decimal = Field(..., gt=0, description="Price in Chinese Yuan (> 0)")
    weight_kg: Optional[Decimal] = Field(Decimal("1.2"), ge=0, description="Estimated weight in kg")
    city: Optional[str] = Field("Москва", description="Delivery city in Russia")
    custom_exchange_rate: Optional[Decimal] = Field(None, gt=0, description="Override rate for simulations")

class PriceBreakdown(BaseModel):
    cny_price: Decimal
    exchange_rate: Decimal
    item_rub_price: Decimal
    
    # International delivery (RaketaCN)
    estimated_weight_kg: Decimal
    min_weight_kg: Decimal
    chargeable_weight_kg: Decimal
    shipping_rub_per_kg: Decimal
    intl_delivery_cost_rub: Decimal
    intl_delivery_formula_ru: str
    
    # Store commission
    commission_type: str
    commission_value: Decimal
    commission_cost_rub: Decimal
    commission_label_ru: str
    
    # Delivery in Russia
    russia_shipping_type: str
    russia_shipping_cost_rub: Decimal
    is_russia_delivery_known: bool
    delivery_city: str
    
    # Totals
    buyout_total_rub: Decimal     # Sum for buyout: item + commission
    grand_total_rub: Decimal      # Total known components
    
    # Display friendly rounded integers
    display_item_rub: int
    display_intl_delivery_rub: int
    display_commission_rub: int
    display_russia_delivery_rub: int
    display_grand_total_rub: int
    
    is_estimate: bool = True
    disclaimer_ru: str

class PricingEngine:
    @staticmethod
    def calculate(
        cny_price: Decimal,
        exchange_rate: Decimal,
        weight_kg: Decimal = Decimal("1.20"),
        shipping_rub_per_kg: Decimal = Decimal("680.00"),
        shipping_min_weight_kg: Decimal = Decimal("0.30"),
        commission_type: str = "percent",
        commission_value: Decimal = Decimal("10.00"),
        commission_fixed_bonus: Decimal = Decimal("0.00"),
        russia_shipping_type: str = "fixed",
        russia_shipping_cost: Decimal = Decimal("350.00"),
        delivery_city: str = "Москва"
    ) -> PriceBreakdown:
        if cny_price <= 0:
            raise ValueError("Цена товара в CNY должна быть строго больше 0")
        if exchange_rate <= 0:
            raise ValueError("Курс юаня должен быть строго больше 0")
        if weight_kg < 0:
            raise ValueError("Вес не может быть отрицательным")

        # 1. Item cost in RUB
        item_rub = round_money(cny_price * exchange_rate)

        # 2. International delivery via RaketaCN
        chargeable_weight = max(weight_kg, shipping_min_weight_kg)
        intl_delivery_cost = round_money(chargeable_weight * shipping_rub_per_kg)
        intl_formula = f"({chargeable_weight:.1f} кг × {int(shipping_rub_per_kg)} ₽/кг)"

        # 3. Store commission
        if commission_type == "percent":
            commission_cost = round_money(item_rub * (commission_value / Decimal("100.0")))
            commission_label = f"Комиссия магазина ({commission_value:.0f}%)"
        elif commission_type == "fixed":
            commission_cost = round_money(commission_value)
            commission_label = "Комиссия магазина"
        elif commission_type == "combo":
            commission_cost = round_money(
                (item_rub * (commission_value / Decimal("100.0"))) + commission_fixed_bonus
            )
            commission_label = f"Комиссия магазина ({commission_value:.0f}% + {int(commission_fixed_bonus)} ₽)"
        else:
            commission_cost = round_money(commission_value)
            commission_label = "Комиссия магазина"

        # 4. Russia delivery
        is_known = True
        if russia_shipping_type == "fixed":
            russia_cost = round_money(russia_shipping_cost)
        elif russia_shipping_type == "unknown":
            russia_cost = Decimal("0.00")
            is_known = False
        else:
            russia_cost = round_money(russia_shipping_cost)

        # 5. Totals
        buyout_total = round_money(item_rub + commission_cost)
        
        # When checkout screen matches reference 2:
        # Reference 2 displays:
        # Item: 600 ¥ * 12.80 = 7680 ₽
        # Delivery (RaketaCN): ≈ 884 ₽ (1.3 kg * 680)
        # Commission: + 1000 ₽
        # Total: ≈ 9 564 ₽ (7680 + 884 + 1000 = 9564)
        grand_total = round_money(item_rub + intl_delivery_cost + commission_cost + (russia_cost if is_known else Decimal("0.00")))

        disclaimer = (
            "Расчёт является предварительной оценкой. Международная доставка может быть уточнена "
            "после фактического взвешивания на складе в Китае. Оплата производится переводом."
        )

        return PriceBreakdown(
            cny_price=cny_price,
            exchange_rate=exchange_rate,
            item_rub_price=item_rub,
            estimated_weight_kg=weight_kg,
            min_weight_kg=shipping_min_weight_kg,
            chargeable_weight_kg=chargeable_weight,
            shipping_rub_per_kg=shipping_rub_per_kg,
            intl_delivery_cost_rub=intl_delivery_cost,
            intl_delivery_formula_ru=intl_formula,
            commission_type=commission_type,
            commission_value=commission_value,
            commission_cost_rub=commission_cost,
            commission_label_ru=commission_label,
            russia_shipping_type=russia_shipping_type,
            russia_shipping_cost_rub=russia_cost,
            is_russia_delivery_known=is_known,
            delivery_city=delivery_city,
            buyout_total_rub=buyout_total,
            grand_total_rub=grand_total,
            display_item_rub=round_rub_int(item_rub),
            display_intl_delivery_rub=round_rub_int(intl_delivery_cost),
            display_commission_rub=round_rub_int(commission_cost),
            display_russia_delivery_rub=round_rub_int(russia_cost),
            display_grand_total_rub=round_rub_int(grand_total),
            is_estimate=True,
            disclaimer_ru=disclaimer
        )
