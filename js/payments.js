/* Bank Account and Credit Card forms
 *
 * These two forms share some common wiring under the Liberapay.payments
 * namespace, and each has unique code under the Liberapay.payments.{cc,ba}
 * namespaces. Each form gets its own page so we only instantiate one of these
 * at a time.
 *
 */

Liberapay.payments = {};


// Common code
// ===========

Liberapay.payments.init = function() {
    $('#delete').submit(Liberapay.payments.deleteRoute);
    $('input[type="digits"]').each(function() {
        var $input = $(this);
        var maxdigits = $input.attr('maxdigits') || $input.attr('digits');
        PaymentCards.restrictNumeric(this, maxdigits);
    });
    $('fieldset.hidden').prop('disabled', true);
    $('button[data-modify]').click(function() {
        var $btn = $(this);
        $($btn.data('modify')).removeClass('hidden').prop('disabled', false);
        $btn.parent().addClass('hidden');
    });
    $('form#payin, form#payout').submit(Liberapay.payments.submit);
}

Liberapay.payments.deleteRoute = function(e) {
    e.stopPropagation();
    e.preventDefault();

    var $this = $(this);
    var confirm_msg = $this.data('confirm');
    if (confirm_msg && !confirm(confirm_msg)) {
        return false;
    }
    jQuery.ajax(
        { url: "/" + Liberapay.username + "/routes/delete.json"
        , data: {network: $this.data('network'), address: $this.data('address')}
        , type: "POST"
        , success: function() { window.location.reload(); }
        , error: Liberapay.error
         }
    );
    return false;
};

Liberapay.payments.wrap = function(f) {
    return function() {
        try {
            return f.apply(this, arguments);
        } catch (e) {
            Liberapay.payments.cc.onError({ResultCode: "1999999", ResultMessage: e})
        }
    }
};

Liberapay.payments.submit = Liberapay.payments.wrap(function(e) {
    e.preventDefault();
    var step2;
    if ($('#bank-account:not(.hidden)').length) step2 = Liberapay.payments.ba.submit;
    if ($('#credit-card:not(.hidden)').length) step2 = Liberapay.payments.cc.submit;

    $('#loading-indicator').remove();
    if (step2 || $('#identity').length) {
        var $bg = $('<div id="loading-indicator">').css({
            'background-color': 'rgba(0, 0, 0, 0.5)',
            'bottom': 0,
            'left': 0,
            'position': 'fixed',
            'right': 0,
            'top': 0,
            'z-index': 1040,
        }).appendTo($('body'));
        var $loading = $('<div class="alert alert-info">');
        $loading.text($(this).data('msg-loading'));
        $loading.appendTo($bg).center('fixed');
    }

    step2 = step2 || Liberapay.payments.onSuccess;
    if ($('#identity').length) {
        Liberapay.payments.id.submit(step2);
    } else {
        step2();
    }
});

Liberapay.payments.error = function(jqXHR, textStatus, errorThrown) {
    $('#loading-indicator').remove();
    if (jqXHR) Liberapay.error(jqXHR, textStatus, errorThrown);
};

Liberapay.payments.onSuccess = function(data) {
    $('#amount').parents('form').off('submit');  // prevents infinite loop
    $('#amount').wrap('<form action="" method="POST">').parent().submit();
};


// Identity
// ========

Liberapay.payments.id = {};

Liberapay.payments.id.submit = function(success) {
    var data = $('#identity').serializeArray();
    jQuery.ajax({
        url: '/'+Liberapay.username+'/identity',
        type: 'POST',
        data: data,
        dataType: 'json',
        success: success,
        error: Liberapay.payments.error,
    });
}


// Bank Accounts
// =============

Liberapay.payments.ba = {};

Liberapay.payments.ba.init = function() {
    Liberapay.payments.init();
    $('fieldset.tab-pane:not(.active)').prop('disabled', true);
    $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
        $($(e.target).attr('href')).prop('disabled', false);
        $($(e.relatedTarget).attr('href')).prop('disabled', true);
    });
};

Liberapay.payments.ba.submit = function () {
    var $ba = $('#bank-account');
    Liberapay.forms.clearInvalid($ba);

    var $iban = $('input[name="IBAN"]');
    var is_iban_invalid = !$('#iban').prop('disabled') && IBAN.isValid($iban.val()) === false;
    Liberapay.forms.setInvalid($iban, is_iban_invalid);

    var $bban = $('#bban input[name="AccountNumber"]');
    var country = $('#bban select[name="Country"]').val();
    var is_bban_invalid = !$('#bban').prop('disabled') && IBAN.isValidBBAN(country, $bban.val()) === false;
    Liberapay.forms.setInvalid($bban, is_bban_invalid);

    var invalids = 0;
    $('input[type="digits"]').each(function() {
        var $input = $(this);
        if ($input.parents(':disabled').length) return;
        var digits = $input.attr('digits');
        var maxdigits = $input.attr('maxdigits') || digits;
        var mindigits = $input.attr('mindigits') || digits;
        var length = $input.val().replace(/[^\d]/g, "").length;
        if (!(/^[\d\s]+$/.test($input.val())) ||
            maxdigits && length > maxdigits ||
            mindigits && length < mindigits) {
            invalids++;
        }
    });

    if (is_bban_invalid || is_iban_invalid || invalids) {
        Liberapay.forms.focusInvalid($ba);
        return Liberapay.payments.error();
    }

    var data = $ba.serializeArray();
    // remove values of controls that are inside a disabled fieldset
    var data2 = [];
    $.each(data, function(i, item) {
        var $element = $ba.find('[name="'+item.name+'"]').filter(function() {
            return $(this).prop('value') == item.value;
        });
        if ($element.length != 1) console.error("$element.length = " + $element.length);
        var $disabled = $element.parents('fieldset:disabled');
        if ($disabled.length == 0) data2.push(item);
    })
    data = data2;
    jQuery.ajax({
        url: '/'+Liberapay.username+'/routes/bank-account.json',
        type: 'POST',
        data: data,
        dataType: 'json',
        success: Liberapay.payments.onSuccess,
        error: Liberapay.payments.error,
    });
};


// Credit Cards
// ============

Liberapay.payments.cc = {};

Liberapay.payments.cc.check = function() {
    Liberapay.forms.clearInvalid($('#credit-card'));

    var card = Liberapay.payments.cc.form.check();
    if (card.status.pan == null) card.status.pan = 'abnormal';
    if (card.status.cvn == null) card.status.cvn = 'valid';
    var card_number_status = card.status.pan.split(':', 1)[0];
    var expiry_status = card.status.expiry.split(':', 1)[0];
    var cvv_status = card.status.cvn.split(':', 1)[0];

    Liberapay.forms.setValidity($('#card_number'), card_number_status);
    Liberapay.forms.setValidity($('#expiration_date'), expiry_status);
    Liberapay.forms.setValidity($('#cvv'), cvv_status);

    return card;
}

Liberapay.payments.cc.init = function() {
    Liberapay.payments.init();
    var form = new PaymentCards.Form(
        document.querySelector('#card_number'),
        document.querySelector('#expiration_date'),
        document.querySelector('#cvv')
    );
    Liberapay.payments.cc.form = form;

    function onBlur() {
        var card = Liberapay.payments.cc.check();
        if (!!card.range) {
            $('.card-brand').text(card.range.brand);
        }
    }
    form.inputs.pan.addEventListener('blur', onBlur);
    form.inputs.expiry.addEventListener('blur', onBlur);
    form.inputs.cvn.addEventListener('blur', onBlur);

    form.inputs.pan.addEventListener('input', function () {
        $('.card-brand').text('');
    });
};

Liberapay.payments.cc.onError = function(response) {
    Liberapay.payments.error();
    var debugInfo = '';
    if (response.ResultMessage == 'CORS_FAIL') {
        var msg = $('#credit-card').data('msg-cors-fail');
    } else {
        var msg = response.ResultMessage;
        var xhr = response.xmlhttp;
        if (xhr && xhr.status === 0) {
            var msg = $('#credit-card').data('msg-cors-fail');
        } else if (xhr) {
            var text = xhr.responseText;
            text = text && text.length > 200 ? text.slice(0, 200) + '...' : text;
            debugInfo = {status: xhr.status, responseText: text};
            debugInfo = ' (Debug info: '+JSON.stringify(debugInfo)+')';
        }
    }
    Liberapay.notification(msg + ' (Error code: '+response.ResultCode+')' + debugInfo, 'error', -1);
};

Liberapay.payments.cc.submit = function() {

    var card = Liberapay.payments.cc.check();
    var status = card.status;
    if (status.pan != 'valid' || status.expiry != 'valid' || status.cvn != 'valid') {
        if (!confirm($('#credit-card').data('msg-confirm-submit'))) {
            Liberapay.payments.error();
            Liberapay.forms.focusInvalid($('#credit-card'));
            return false;
        }
    }

    var cardData = {
        cardNumber: card.pan,
        cardCvx: card.cvn,
        cardExpirationDate: card.expiry,
    };

    jQuery.ajax({
        url: '/'+Liberapay.username+'/routes/credit-card.json',
        type: "POST",
        data: {CardType: 'CB_VISA_MASTERCARD', Currency: 'EUR'},
        dataType: "json",
        success: Liberapay.payments.cc.register(cardData),
        error: Liberapay.payments.error,
    });
    return false;
};

Liberapay.payments.cc.register = function (cardData) {
    return Liberapay.payments.wrap(function (cardRegistrationData) {
        cardRegistrationData.Id = cardRegistrationData.id;
        delete cardRegistrationData.id;
        mangoPay.cardRegistration.init(cardRegistrationData);
        mangoPay.cardRegistration.registerCard(cardData, Liberapay.payments.cc.associate, Liberapay.payments.cc.onError);
    })
};

Liberapay.payments.cc.associate = function (response) {
    /* The request to tokenize the card succeeded. Now we need to associate it
     * to the participant in our DB.
     */
    jQuery.ajax({
        url: '/'+Liberapay.username+'/routes/credit-card.json',
        type: "POST",
        data: {CardId: response.CardId, keep: $('input#keep').prop('checked')},
        dataType: "json",
        success: Liberapay.payments.onSuccess,
        error: Liberapay.payments.error,
    });
};
