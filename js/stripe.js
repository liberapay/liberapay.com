Liberapay.stripe_init = function() {
    var $form = $('form#stripe');
    if ($form.length !== 1) return;
    $('fieldset.hidden').prop('disabled', true);
    $('button[data-modify]').click(function() {
        var $btn = $(this);
        $($btn.data('modify')).removeClass('hidden').prop('disabled', false);
        $btn.parent().addClass('hidden');
    });

    var $errorElement = $('#stripe-errors');
    var stripe = null;
    if (window.Stripe) {
        stripe = Stripe($form.data('stripe-pk'));
    } else {
        $errorElement.text($form.attr('data-msg-stripe-missing'));
        $errorElement.hide().fadeIn()[0].scrollIntoView();
    }

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
        return /AD|AL|BL|CH|GB|GG|GI|IM|JE|MC|MD|ME|MK|NC|PF|PM|SM|TF|VA|WF/.test(
            $container.data('country')
        );
    }

    if ($container.length === 1) {
        var elements = stripe.elements({
            onBehalfOf: $form.data('stripe-on-behalf-of') || undefined,
        });
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
    }

    Liberapay.stripe_before_account_submit = async function() {
        const response = await stripe.createToken('account', {
            tos_shown_and_accepted: true,
        });
        if (response.token) {
            $form.find('input[name="account_token"]').remove();
            var $pm_id_input = $('<input type="hidden" name="account_token">');
            $pm_id_input.val(response.token.id);
            $pm_id_input.appendTo($form);
            return true;
        } else {
            $errorElement.text(response.error || response);
            $errorElement.hide().fadeIn()[0].scrollIntoView();
            return false;
        }
    }

    Liberapay.stripe_before_element_submit = async function() {
        // If the Payment Element is hidden, simply let the browser submit the form
        if ($container.parents('.hidden').length > 0) {
            console.debug("stripe_before_element_submit: ignoring hidden payment element");
            return true;
        }
        // If Stripe.js is missing, stop the submission
        if (!stripe) {
            $errorElement.hide().fadeIn()[0].scrollIntoView();
            return false;
        }
        // Create the PaymentMethod
        var pmType = element_type;
        if (element_type == 'iban') {
            pmType = 'sepa_debit';
            if (is_postal_address_required() && !is_postal_address_filled()) {
                $postal_address_alert.removeClass('hidden').hide().fadeIn()[0].scrollIntoView();
                return false;
            }
        }
        var local_address = $postal_address_local.val();
        local_address = local_address ? local_address.split(/(?:\r\n?|\n)/g) : [undefined];
        if (local_address.length === 1) {
            local_address.push(undefined);
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
        var result = await stripe.createPaymentMethod(pmType, element, pmData);
        // If the PaymentMethod has been created, submit the form. Otherwise,
        // display an error.
        if (result.paymentMethod && result.paymentMethod.id) {
            $form.find('input[name="route"]').remove();
            $form.find('input[name="stripe_pm_id"]').remove();
            var $pm_id_input = $('<input type="hidden" name="stripe_pm_id">');
            $pm_id_input.val(result.paymentMethod.id);
            $pm_id_input.appendTo($form);
            return true;
        } else {
            var msg = '' + (result.error ? result.error.message : result);
            $errorElement.text(msg)[0].scrollIntoView();
            return false;
        }
    };
};
