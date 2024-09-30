UPDATE exchange_routes SET is_default_for = 'EUR', is_default = null WHERE network = 'stripe-sdd' AND is_default;
