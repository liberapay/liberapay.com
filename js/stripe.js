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
    var $postal_address_alert = $form.find('.msg-postal-address-required');
    var $postal_address_country = $form.find('select[name="postal_address.country"]');
    var $postal_address_region = $form.find('input[name="postal_address.region"]');
    var $postal_address_city = $form.find('input[name="postal_address.city"]');
    var $postal_address_code = $form.find('input[name="postal_address.postal_code"]');
    var $postal_address_local = $form.find('textarea[name="postal_address.local_address"]');
    function is_postal_address_filled() {
        return $postal_address_country.val() > '' &&
               $postal_address_city.val() > '' &&
               $postal_address_code.val() > '' &&
               $postal_address_local.val() > '';
    }
    function is_postal_address_required() {
        return /AD|BL|CH|GB|GG|GI|IM|JE|MC|NC|PF|PM|SM|TF|VA|WF/.test($container.data('country'));
    }

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
        if (event.country) {
            $container.data('country', event.country);
            if (!is_postal_address_required()) {
                $postal_address_alert.hide();
            }
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
        var pmType = element_type;
        if (element_type == 'iban') {
            pmType = 'sepa_debit';
            if (is_postal_address_required() && !is_postal_address_filled()) {
                $postal_address_alert.removeClass('hidden').hide().fadeIn()[0].scrollIntoView();
                return;
            }
        }
        var local_address = $postal_address_local.val();
        local_address = !!local_address ? local_address.split(/(?:\r\n?|\n)/g) : [null];
        if (local_address.length === 1) {
            local_address.push(null);
        }
        var pmData = {
            billing_details: {
                address: {
                    city: $postal_address_city.val(),
                    country: $postal_address_country.val(),
                    line1: local_address[0],
                    line2: local_address[1],
                    postal_code: $postal_address_code.val(),
                    state: $postal_address_region.val(),
                },
                email: $form.find('input[name="owner.email"]').val(),
                name: $form.find('input[name="owner.name"]').val(),
            }
        };
        stripe.createPaymentMethod(pmType, element, pmData).then(Liberapay.wrap(function(result) {
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
