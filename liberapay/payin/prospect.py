from ..constants import PAYIN_AMOUNTS, PERIOD_CONVERSION_MAP


class PayinProspect:
    """Represents a prospective payment.
    """

    __slots__ = (
        'tips', 'provider', 'currency', 'period',
        'one_periods_worth', 'one_weeks_worth', 'one_months_worth', 'one_years_worth',
        'twelve_years_worth',
        'min_acceptable_amount', 'moderate_fee_amount', 'max_acceptable_amount',
        'min_proposed_amount', 'moderate_proposed_amount', 'low_fee_amount',
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
        self.twelve_years_worth = self.one_years_worth * 12
        if self.period == 'weekly':
            self.one_months_worth = (self.one_weeks_worth * 4).round()
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
            self.twelve_years_worth
        )
        self.min_proposed_amount = max(
            self.min_acceptable_amount,
            self.one_months_worth,
            self.one_periods_worth
        )
        self.moderate_proposed_amount = min(
            max(
                self.moderate_fee_amount,
                self.one_months_worth,
                self.one_periods_worth
            ),
            self.twelve_years_worth
        )
        periodic_amounts = [
            self.one_months_worth,
            (self.one_years_worth / 4).round(),
            (self.one_years_worth / 2).round(),
            self.one_years_worth,
        ]
        recommended_amounts = [
            a for a in periodic_amounts if (
                a >= self.low_fee_amount and
                a >= self.moderate_proposed_amount * 2 and
                a <= self.max_acceptable_amount
            )
        ]
        self.suggested_amounts = sorted(set((
            self.min_proposed_amount,
            self.moderate_proposed_amount,
            *recommended_amounts
        )))

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
