Liberapay.stripe_init = function() {
    var $form = $('form#stripe');
    if ($form.length === 0) return;
    $('fieldset.hidden').prop('disabled', true);
    $('button[data-modify]').click(function() {
        var $btn = $(this);
        $($btn.data('modify')).removeClass('hidden').prop('disabled', false);
        $btn.parent().addClass('hidden');
    });

    var $cardElement = $('#card-element');
    var stripe = Stripe($form.data('stripe-pk'));
    var elements = stripe.elements();
    var card = elements.create('card', {style: {
        base: {
            color: $cardElement.css('color'),
            fontFamily: $cardElement.css('font-family'),
            fontSize: $cardElement.css('font-size'),
            lineHeight: $cardElement.css('line-height'),
        }
    }});
    card.mount('#card-element');
    var $errorElement = $('#card-errors');
    card.addEventListener('change', function(event) {
        if (event.error) {
            $errorElement.text(event.error.message);
        } else {
            $errorElement.text('');
        }
    });

    var submitting = false;
    $form.submit(Liberapay.wrap(function(e) {
        if (submitting) {
            submitting = false;
            return;
        }
        e.preventDefault();
        if ($cardElement.parents('.hidden').length > 0) {
            submitting = true;
            $form.attr('action', '').submit();
            return;
        }
        stripe.createToken(card).then(Liberapay.wrap(function(result) {
            if (result.error) {
                $errorElement.text(result.error.message);
            } else {
                submitting = true;
                $form.find('input[name="route"]').remove();
                $form.find('input[name="token"]').remove();
                var $hidden_input = $('<input type="hidden" name="token">');
                $hidden_input.val(result.token.id);
                $form.append($hidden_input);
                $form.attr('action', '').submit();
            }
        }));
    }));
};
