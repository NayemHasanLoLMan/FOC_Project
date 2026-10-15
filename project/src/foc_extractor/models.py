from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class LineItem:
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    weight_kg: Optional[float] = None
    hs_code: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    source_page: Optional[int] = None
    confidence: Optional[float] = None
    source_refs: list[str] = field(default_factory=list)

@dataclass
class FOCData:
    source_file: str
    ocr_backend: Optional[str] = None
    pages_processed: Optional[int] = None
    pages_total: Optional[int] = None
    invoice_number: Optional[str] = None
    export_date: Optional[str] = None
    consignee: Optional[str] = None
    consignee_address: Optional[str] = None
    shipping_marks: Optional[str] = None
    carton_range: Optional[str] = None
    destination_country: Optional[str] = None
    destination_city: Optional[str] = None
    port_of_discharge: Optional[str] = None
    shipment_terms: Optional[str] = None
    package_count: Optional[int] = None
    gross_weight_kg: Optional[float] = None
    currency: str = "USD"
    total_value: Optional[float] = None
    template_type: Optional[str] = None
    items: list[LineItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
