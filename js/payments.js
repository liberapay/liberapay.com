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
    $('input[type="digits"]').on('keypress', function(e) {
        if (e.metaKey || e.ctrlKey || e.which < 32) return true;
        if (!(/^[\d\s]+$/.test(String.fromCharCode(e.which)))) e.preventDefault();
        var $input = $(this);
        var length = $input.val().replace(/[^\d]/g, "").length;
        var maxdigits = $input.attr('maxdigits') || $input.attr('digits');
        if (maxdigits && length >= maxdigits) e.preventDefault();
    });
    $('fieldset.hidden').prop('disabled', true);
    $('button[data-modify]').click(function() {
        var $btn = $(this);
        $($btn.data('modify')).removeClass('hidden').prop('disabled', false);
        $btn.parent().addClass('hidden');
    });
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

Liberapay.payments.submit = function(e) {
    e.preventDefault();
    $('#loading-indicator').remove();
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

    var step2 = Liberapay.payments.onSuccess;
    if ($('#bank-account:not(.hidden)').length) step2 = Liberapay.payments.ba.submit;
    if ($('#credit-card:not(.hidden)').length) step2 = Liberapay.payments.cc.submit;
    if ($('#identity').length) {
        Liberapay.payments.id.submit(step2);
    } else {
        step2();
    }
};

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
    $('form#payout').submit(Liberapay.payments.submit);
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

Liberapay.payments.cc.init = function() {
    Liberapay.payments.init();
    Liberapay.payments.cc.formatInputs(
        $('#card_number'),
        $('#expiration_date'),
        $('#cvv')
    );
    $('form#payin').submit(Liberapay.payments.submit);
};

Liberapay.payments.cc.onError = function(response) {
    Liberapay.payments.error();
    if (response.ResultMessage == 'CORS_FAIL') {
        var msg = $('#credit-card').data('msg-cors-fail');
    } else {
        var msg = response.ResultMessage;
    }
    Liberapay.notification(msg + ' (Error code: '+response.ResultCode+')', 'error', -1);
};

Liberapay.payments.cc.formatInputs = function (cardNumberInput, expirationDateInput, cvvInput) {
    /* This code was originally taken from https://github.com/wangjohn/creditly */

    function getInputValue(e, element) {
        var inputValue = element.val().trim();
        inputValue = inputValue + String.fromCharCode(e.which);
        return inputValue.replace(/[^\d]/g, "");
    }

    function isEscapedKeyStroke(e) {
        return e.metaKey || e.ctrlKey || e.which < 32;
    }

    function isNumberEvent(e) {
        return (/^\d+$/.test(String.fromCharCode(e.which)));
    }

    function onlyAllowNumeric(e, maximumLength, element) {
        e.preventDefault();
        // Ensure that it is a number and stop the keypress
        if (!isNumberEvent(e)) {
            return false;
        }
        return true;
    }

    var isAmericanExpress = function(number) {
        return number.match("^(34|37)");
    };

    function shouldProcessInput(e, maximumLength, element) {
        var target = e.currentTarget;
        if (getInputValue(e, element).length > maximumLength) {
            e.preventDefault();
            return false;
        }
        if ((target.selectionStart !== target.value.length)) {
            return false;
        }
        return (!isEscapedKeyStroke(e)) && onlyAllowNumeric(e, maximumLength, element);
    }

    function addSeparators(string, positions, separator) {
        var separator = separator || ' ';
        var parts = []
        var j = 0;
        for (var i=0; i<positions.length; i++) {
            if (string.length > positions[i]) {
                parts.push(string.slice(j, positions[i]));
                j = positions[i];
            } else {
                break;
            }
        }
        parts.push(string.slice(j));
        return parts.join(separator);
    }

    var americanExpressSpaces = [4, 10, 15];
    var defaultSpaces = [4, 8, 12, 16];

    cardNumberInput.on("keypress", function(e) {
        var number = getInputValue(e, cardNumberInput);
        var isAmericanExpressCard = isAmericanExpress(number);
        var maximumLength = (isAmericanExpressCard ? 15 : 16);
        if (shouldProcessInput(e, maximumLength, cardNumberInput)) {
            var newInput;
            newInput = isAmericanExpressCard ? addSeparators(number, americanExpressSpaces) : addSeparators(number, defaultSpaces);
            cardNumberInput.val(newInput);
        }
    });

    expirationDateInput.on("keypress", function(e) {
        var maximumLength = 4;
        if (shouldProcessInput(e, maximumLength, expirationDateInput)) {
            var newInput = getInputValue(e, expirationDateInput);
            expirationDateInput.val(addSeparators(newInput, [2], '/'));
        }
    });

    cvvInput.on("keypress", function(e) {
        var number = getInputValue(e, cardNumberInput);
        var isAmericanExpressCard = isAmericanExpress(number);
        var maximumLength = (isAmericanExpressCard ? 4 : 3);
        if (shouldProcessInput(e, maximumLength, cvvInput)) {
            var newInput = getInputValue(e, cvvInput);
            cvvInput.val(newInput);
        }
    });
}

Liberapay.payments.cc.submit = function() {

    Liberapay.forms.clearInvalid($('#credit-card'));

    function val(field) {
        return $('#'+field).val().replace(/[^\d]/g, '');
    }

    var cardData = {
        cardType: 'CB_VISA_MASTERCARD',
        cardNumber: val('card_number'),
        cardCvx: val('cvv'),
        cardExpirationDate: val('expiration_date'),
    };

    var is_card_number_invalid = mangoPay._validation._cardNumberValidator._validate(cardData.cardNumber) !== true;
    var is_expiry_invalid = mangoPay._validation._expirationDateValidator._validate(cardData.cardExpirationDate, new Date()) !== true;

    Liberapay.forms.setInvalid($('#card_number'), is_card_number_invalid);
    Liberapay.forms.setInvalid($('#expiration_date'), is_expiry_invalid);

    if (is_card_number_invalid || is_expiry_invalid) {
        Liberapay.payments.error();
        Liberapay.forms.focusInvalid($('#credit-card'));
        return false;
    }

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
    return function (cardRegistrationData) {
        cardRegistrationData.Id = cardRegistrationData.id;
        delete cardRegistrationData.id;
        mangoPay.cardRegistration.init(cardRegistrationData);
        mangoPay.cardRegistration.registerCard(cardData, Liberapay.payments.cc.associate, Liberapay.payments.cc.onError);
    }
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
