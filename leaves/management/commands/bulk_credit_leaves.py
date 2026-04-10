from django.core.management.base import BaseCommand
from leaves.services.accrual import run_bulk_credit, run_monthly_accrual
from datetime import date


class Command(BaseCommand):
    help = 'Bulk credit leaves for a year'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=date.today().year)
        parser.add_argument('--accrual', action='store_true', help='Also run monthly accrual')

    def handle(self, *args, **options):
        year = options['year']

        self.stdout.write(f'Running bulk credit for year {year}...')
        results = run_bulk_credit(year)
        self.stdout.write(f'Bulk credit: {len(results)} entries created.')

        if options['accrual']:
            self.stdout.write('Running monthly accrual...')
            accrual_results = run_monthly_accrual(date.today())
            self.stdout.write(f'Accrual: {len(accrual_results)} entries created.')

        from leaves.models import LeaveBalance
        total_balances = LeaveBalance.objects.filter(year=year).count()
        self.stdout.write(self.style.SUCCESS(f'Done. {total_balances} balance records for year {year}.'))
