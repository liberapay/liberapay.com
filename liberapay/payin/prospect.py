from decimal import Decimal, ROUND_DOWN, ROUND_UP

from ..constants import PAYIN_AMOUNTS, PERIOD_CONVERSION_MAP


class PayinProspect:
    """Represents a prospective payment.
    """

    __slots__ = (
        'tips', 'provider', 'currency', 'period',
        'one_periods_worth', 'one_weeks_worth', 'one_months_worth', 'one_years_worth',
        'twenty_years_worth',
        'min_acceptable_amount', 'moderate_fee_amount', 'low_fee_amount', 'max_acceptable_amount',
        'min_proposed_amount', 'moderate_proposed_amount', 'low_fee_proposed_amount',
        'suggested_amounts',
    )

    def __init__(self, tips, provider):
        """This method computes the suggested payment amounts.

        Args:
            tips (list): the donations to fund
            provider (str): the payment processor ('paypal' or 'stripe')

        """
        self.tips = tips
        self.provider = provider
        self.currency = tips[0].amount.currency
        periods = set(tip.period for tip in tips)
        self.period = (
            tips[0].period if len(periods) == 1 else
            'monthly' if 'monthly' in periods else
            'weekly'
        )
        self.one_periods_worth = sum(
            tip.periodic_amount * PERIOD_CONVERSION_MAP[(tip.period, self.period)]
            for tip in tips
        ).round()
        self.one_weeks_worth = sum(tip.amount for tip in tips).round()
        self.one_years_worth = sum(
            tip.periodic_amount * PERIOD_CONVERSION_MAP[(tip.period, 'yearly')]
            for tip in tips
        ).round()
        self.twenty_years_worth = self.one_years_worth * 20
        if self.period == 'weekly':
            # For weekly donations we round up the monthly amount to 5 weeks.
            self.one_months_worth = (self.one_weeks_worth * 5).round()
        elif self.period == 'monthly':
            self.one_months_worth = self.one_periods_worth
        else:
            self.one_months_worth = (self.one_years_worth / 12).round()
        standard_amounts = PAYIN_AMOUNTS[provider]
        self.min_acceptable_amount = max(
            standard_amounts['min_acceptable'][self.currency],
            self.one_weeks_worth
        )
        self.moderate_fee_amount = max(
            standard_amounts['min_recommended'][self.currency],
            self.one_weeks_worth
        )
        self.low_fee_amount = standard_amounts['low_fee'][self.currency]
        self.max_acceptable_amount = min(
            standard_amounts['max_acceptable'][self.currency],
            self.twenty_years_worth
        )
        self.min_proposed_amount = min(
            max(
                self.round_to_period(self.min_acceptable_amount, threshold=0),
                self.one_months_worth,
                self.one_periods_worth
            ),
            self.max_acceptable_amount
        )
        self.moderate_proposed_amount = min(
            max(
                self.round_to_period(self.moderate_fee_amount),
                self.one_months_worth,
                self.one_periods_worth
            ),
            self.twenty_years_worth,
            self.max_acceptable_amount
        )
        self.low_fee_proposed_amount = min(
            max(
                self.round_to_period(self.low_fee_amount),
                self.moderate_proposed_amount * 2
            ),
            self.max_acceptable_amount
        )
        if self.period == 'yearly':
            suggested_amounts = [
                self.one_years_worth,
                self.one_years_worth * 2,
            ]
        else:
            suggested_amounts = [
                self.one_months_worth,
                (self.one_years_worth / 4).round(),
                (self.one_years_worth / 2).round(),
                self.one_years_worth,
            ]
        if suggested_amounts[-1] < self.low_fee_proposed_amount:
            if suggested_amounts[-1] < self.moderate_proposed_amount:
                suggested_amounts.append(self.moderate_proposed_amount)
            suggested_amounts.append(self.low_fee_proposed_amount)
        suggested_amounts = [
            a for a in suggested_amounts
            if a >= self.moderate_proposed_amount and a <= self.max_acceptable_amount
        ]
        suggested_amounts = sorted(set((
            self.min_proposed_amount,
            *suggested_amounts
        )))
        self.suggested_amounts = [
            suggested_amounts[i] for i in range(len(suggested_amounts))
            if i == 0 or suggested_amounts[i] >= (suggested_amounts[i-1] * Decimal('1.5'))
        ]

    def round_to_period(self, amount, threshold=Decimal('0.15')):
        """Return the periodic amount “closest” to the given target amount.

        The `threshold` argument controls the rounding behavior. The default
        value strongly favors rounding up instead of down.
        """
        n_periods = amount / self.one_periods_worth
        n_periods = n_periods.to_integral_value(rounding=(
            ROUND_UP if n_periods % 1 > threshold else ROUND_DOWN
        ))
        return self.one_periods_worth * n_periods

    # The properties below exist because Jinja doesn't support list comprehensions.

    @property
    def recipient_links(self):
        return [tip.tippee_p.link() for tip in self.tips]

    @property
    def recipient_names(self):
        return [tip.tippee_p.username for tip in self.tips]

    @property
    def tip_ids(self):
        return ','.join(str(tip.id) for tip in self.tips)
