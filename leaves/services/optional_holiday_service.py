from datetime import date
from leaves.models import OptionalHoliday, OptionalHolidaySelection


def get_holidays(year=None):
    if year is None:
        year = date.today().year
    return OptionalHoliday.objects.filter(year=year, is_active=True)


def select_holiday(actor, holiday_id):
    holiday = OptionalHoliday.objects.get(id=holiday_id)
    sel, created = OptionalHolidaySelection.objects.get_or_create(
        employee=actor, holiday=holiday, defaults={'status': 'PENDING'}
    )
    return sel


def approve_selection(actor, selection_id):
    sel = OptionalHolidaySelection.objects.get(id=selection_id)
    sel.status = 'APPROVED'
    sel.approved_by = actor
    sel.save()
    return sel


def create_holiday(actor, name, date_val, year=None, description=''):
    if year is None:
        year = date_val.year if hasattr(date_val, 'year') else date.today().year
    return OptionalHoliday.objects.create(
        name=name, date=date_val, year=year,
        description=description, created_by=actor,
    )
