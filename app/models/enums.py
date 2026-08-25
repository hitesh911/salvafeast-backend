import enum


class OrderType(str, enum.Enum):
    dine_in = "dine_in"
    pickup = "pickup"
    pre_order = "pre_order"
    counter = "counter"


class OrderStatus(str, enum.Enum):
    payment_review = "payment_review"
    placed = "placed"
    accepted = "accepted"
    preparing = "preparing"
    ready = "ready"
    served = "served"
    completed = "completed"
    cancelled = "cancelled"


class PaymentStatus(str, enum.Enum):
    unpaid = "unpaid"
    paid = "paid"


class PaymentMethod(str, enum.Enum):
    upi = "upi"
    cash = "cash"
    card = "card"
    other = "other"


class PaymentCollection(str, enum.Enum):
    upi = "upi"
    counter = "counter"


class CancelledBy(str, enum.Enum):
    user = "user"
    staff = "staff"


class CancelRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SubscriptionStatus(str, enum.Enum):
    trial = "trial"
    active = "active"
    past_due = "past_due"
    cancelled = "cancelled"


class BillingInterval(str, enum.Enum):
    monthly = "monthly"
    yearly = "yearly"


class DietaryType(str, enum.Enum):
    veg = "veg"
    vegan = "vegan"
    non_veg = "non_veg"


class PlatformInvoiceStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    paid = "paid"
    overdue = "overdue"


class DiscountType(str, enum.Enum):
    flat = "flat"
    percentage = "percentage"


class EmbedPlatform(str, enum.Enum):
    instagram = "instagram"
    youtube = "youtube"


class VerificationStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class OutletType(str, enum.Enum):
    restaurant = "restaurant"
    cafe = "cafe"
    cloud_kitchen = "cloud_kitchen"
    bakery = "bakery"
    other = "other"


class UserGender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"
    prefer_not_to_say = "prefer_not_to_say"
