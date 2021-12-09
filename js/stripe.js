Liberapay.stripe_init = function() {
    var $form = $('form#stripe');
    if ($form.length === 1) Liberapay.stripe_form_init($form);
    var $next_action = $('#stripe_next_action');
    if ($next_action.length === 1) Liberapay.stripe_next_action($next_action);
};

Liberapay.stripe_form_init = function($form) {
    $('fieldset.hidden').prop('disabled', true);
    $('button[data-modify]').click(function() {
        var $btn = $(this);
        $($btn.data('modify')).removeClass('hidden').prop('disabled', false);
        $btn.parent().addClass('hidden');
    });

    var $container = $('#stripe-element');
    var stripe = Stripe($form.data('stripe-pk'));
    var elements = stripe.elements();
    var element_type = $container.data('type');
    var options = {style: {
        base: {
            color: rgb_to_hex($container.css('color')),
            fontFamily: $container.css('font-family'),
            fontSize: $container.css('font-size'),
            lineHeight: $container.css('line-height'),
        }
    }};
    if (element_type == 'iban') {
        options.supportedCountries = ['SEPA'];
    }
    var element = elements.create(element_type, options);
    element.mount('#stripe-element');
    var $errorElement = $('#stripe-errors');
    element.addEventListener('change', function(event) {
        if (event.error) {
            $errorElement.text(event.error.message);
        } else {
            $errorElement.text('');
        }
    });

    var submitting = false;
    $form.submit(Liberapay.wrap(function(e) {
        if ($form.data('js-submit-disable')) {
            e.preventDefault();
            return false;
        }
        if (submitting) {
            submitting = false;
            // Prevent submitting again
            $form.data('js-submit-disable', true);
            var $inputs = $form.find(':not(:disabled)');
            setTimeout(function () { $inputs.prop('disabled', true); }, 100);
            // Unlock if the user comes back to the page
            $(window).on('focus pageshow', function () {
                $form.data('js-submit-disable', false);
                $inputs.prop('disabled', false);
            });
            return;
        }
        e.preventDefault();
        if ($container.parents('.hidden').length > 0) {
            submitting = true;
            $form.submit();
            return;
        }
        var local_address = $form.find('input[name="postal_address.local_address"]').val();
        local_address = !!local_address ? local_address.split(/(?:\r\n?|\n)/g) : [null];
        if (local_address.length === 1) {
            local_address.push(null);
        }
        if (element_type == 'iban') {
            var tokenData = {};
            tokenData.currency = 'EUR';
            tokenData.account_holder_name = $form.find('input[name="owner.name"]').val();
            tokenData.address_country = $form.find('input[name="postal_address.country"]').val();
            tokenData.address_state = $form.find('input[name="postal_address.region"]').val();
            tokenData.address_city = $form.find('input[name="postal_address.city"]').val();
            tokenData.address_zip = $form.find('input[name="postal_address.postal_code"]').val();
            tokenData.address_line1 = local_address[0];
            tokenData.address_line2 = local_address[1];
            stripe.createToken(element, tokenData).then(Liberapay.wrap(function(result) {
                if (result.error) {
                    $errorElement.text(result.error.message);
                } else {
                    submitting = true;
                    $form.find('input[name="route"]').remove();
                    $form.find('input[name="token"]').remove();
                    var $hidden_input = $('<input type="hidden" name="token">');
                    $hidden_input.val(result.token.id);
                    $form.append($hidden_input);
                    $form.submit();
                }
            }));
        } else if (element_type == 'card') {
            var pmData = {
                billing_details: {
                    address: {
                        city: $form.find('input[name="postal_address.city"]').val(),
                        country: $form.find('input[name="postal_address.country"]').val(),
                        line1: local_address[0],
                        line2: local_address[1],
                        postal_code: $form.find('input[name="postal_address.postal_code"]').val(),
                        state: $form.find('input[name="postal_address.region"]').val(),
                    },
                    email: $form.find('input[name="owner.email"]').val(),
                    name: $form.find('input[name="owner.name"]').val(),
                }
            };
            stripe.createPaymentMethod('card', element, pmData).then(Liberapay.wrap(function(result) {
                if (result.error) {
                    $errorElement.text(result.error.message);
                } else {
                    submitting = true;
                    $form.find('input[name="route"]').remove();
                    $form.find('input[name="stripe_pm_id"]').remove();
                    var $hidden_input = $('<input type="hidden" name="stripe_pm_id">');
                    $hidden_input.val(result.paymentMethod.id);
                    $form.append($hidden_input);
                    $form.submit();
                }
            }));
        }
    }));
    $form.attr('action', '');
};

Liberapay.stripe_next_action = function ($next_action) {
    stripe.handleCardAction($next_action.data('client_secret')).then(function (result) {
        if (result.error) {
            $next_action.addClass('alert alert-danger').text(result.error.message);
        } else {
            window.location.reload();
        }
    })
};
