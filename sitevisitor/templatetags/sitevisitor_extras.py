from django import template

register = template.Library()

@register.filter(name="replace_chars")
def replace_chars(value: str, arg: str = "/-") -> str:
    """Replace characters in *value* according to *arg*.

    The default behavior (when **arg** is omitted) converts all forward slashes
    ("/") to hyphens ("-").

    Custom usage: ``{{ value|replace_chars:"old:new" }}`` will replace **old**
    with **new**.  Only the first two characters around the colon are read so
    keep them concise.
    """
    if not isinstance(value, str):
        value = str(value)

    # When arg is provided in the form "old:new" perform that replacement.
    if arg and ":" in arg:
        old, new = arg.split(":", 1)
        return value.replace(old, new)

    # Default replacement: replace the first char (old) with the second (new).
    if len(arg) >= 2:
        old, new = arg[0], arg[1]
        return value.replace(old, new)

    # Fallback: if arg malformed, just return value unchanged
    return value.replace("/", "-")

@register.simple_tag(name="plan_price")
def plan_price(duration_days):
    """Return the price for the active SubscriptionPlan that matches *duration_days*.

    Usage in templates::

        <span>${% plan_price 30 %}</span>

    This will print the price without trailing zeros (e.g., ``15`` instead of ``15.00``).
    """
    from adminpanel.models import SubscriptionPlan

    try:
        duration_int = int(duration_days)
    except (ValueError, TypeError):
        return ""

    plan = SubscriptionPlan.objects.filter(duration_days=duration_int, is_active=True).first()
    if not plan:
        # Fallback: allow off-by-one (e.g., 30 vs 31) or nearest duration
        plan = (
            SubscriptionPlan.objects.filter(
                duration_days__gte=duration_int - 1,
                duration_days__lte=duration_int + 1,
                is_active=True,
            )
            .order_by("duration_days")
            .first()
        )
    if not plan:
        return ""

    price = plan.price
    # Convert Decimal to string and strip unnecessary zeros/decimal point
    price_str = ("%0.2f" % price).rstrip("0").rstrip(".")
    return price_str
