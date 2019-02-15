Liberapay.stripe_init = function() {
    var $form = $('form#stripe');
    if ($form.length === 0) return;
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
            color: $container.css('color'),
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
        var tokenData = {};
        if (element_type == 'iban') {
            tokenData.currency = 'EUR';
            tokenData.account_holder_name = $('input[name="owner.name"]').val();
        } else if (element_type == 'card') {
            tokenData.name = $('input[name="owner.name"]').val();
        }
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
    }));
    $form.attr('action', '');
};
