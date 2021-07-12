DELETE FROM notifications WHERE event IN (
    'dispute',
    'low_balance',
    'payin_bankwire_created',
    'payin_bankwire_expired',
    'payin_bankwire_failed',
    'payin_bankwire_succeeded',
    'payin_directdebit_failed',
    'payin_directdebit_succeeded'
);
