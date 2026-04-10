from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from leaves.models import EmployeeOverride
from leaves.services.config_resolver import get_effective_config
from .test_helpers import *


class TestConfigResolver(TestCase):
    def setUp(self):
        setup_company_config()
        self.dept = create_test_department()
        self.desg = create_test_designation()
        self.emp = create_test_employee(department=self.dept, designation=self.desg)
        self.lt = create_test_leave_type()

    def test_no_override(self):
        config = get_effective_config(self.emp, self.lt)
        self.assertEqual(config['entitlement_days'], 8)
        self.assertFalse(config['block_accrual'])
        self.assertFalse(config['block_application'])

    def test_block_accrual_override(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            block_accrual=True, effective_from=date.today(),
            reason='Test', created_via='API',
        )
        config = get_effective_config(self.emp, self.lt)
        self.assertTrue(config['block_accrual'])

    def test_modify_entitlement(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            modify_entitlement=Decimal('10.0'), effective_from=date.today(),
            reason='Test', created_via='API',
        )
        config = get_effective_config(self.emp, self.lt)
        self.assertEqual(config['entitlement_days'], Decimal('10.0'))

    def test_waive_restriction(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            waive_restriction={'probation_eligible': True},
            effective_from=date.today(), reason='Test', created_via='API',
        )
        config = get_effective_config(self.emp, self.lt)
        self.assertTrue(config['probation_eligible'])

    def test_custom_approval_chain(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            custom_approval_chain=['HR'],
            effective_from=date.today(), reason='Test', created_via='API',
        )
        config = get_effective_config(self.emp, self.lt)
        self.assertEqual(config['approval_chain'], ['HR'])

    def test_expired_override_ignored(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            block_application=True,
            effective_from=date.today() - timedelta(days=30),
            effective_to=date.today() - timedelta(days=1),
            reason='Test', created_via='API',
        )
        config = get_effective_config(self.emp, self.lt)
        self.assertFalse(config['block_application'])

    def test_future_override_ignored(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            block_application=True,
            effective_from=date.today() + timedelta(days=10),
            reason='Test', created_via='API',
        )
        config = get_effective_config(self.emp, self.lt)
        self.assertFalse(config['block_application'])

    def test_null_leave_type_applies_to_all(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=None,
            block_application=True,
            effective_from=date.today(), reason='Test', created_via='API',
        )
        config = get_effective_config(self.emp, self.lt)
        self.assertTrue(config['block_application'])
