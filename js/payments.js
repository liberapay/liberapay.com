Liberapay.payments = {};


// Common code
// ===========

Liberapay.payments.init = function() {
    var $form = $('form#payout');
    if ($form.length === 0) return;
    $('fieldset.hidden').prop('disabled', true);
    $('button[data-modify]').click(function() {
        var $btn = $(this);
        $($btn.data('modify')).removeClass('hidden').prop('disabled', false);
        $btn.parent().addClass('hidden');
    });
    Liberapay.payments.user_slug = $form.data('user-slug');
    $form.submit(Liberapay.payments.submit);
    $('select.country').on('change', function () {
        var newValue = $(this).val();
        $(this).data('value-was-copied', null);
        if (this.name != 'CountryOfResidence') return;
        $('select.country').val(function (i, value) {
            if (value == '' || $(this).data('value-was-copied')) {
                $(this).data('value-was-copied', true);
                return newValue;
            }
            return value;
        })
    });
    Liberapay.payments.ba.init();
    Liberapay.payments.cc.init();
}

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
    if (data && data.route_id) {
        $('#amount input[name="route_id"]').val(data.route_id);
    }
    $('#amount').parents('form').off('submit');  // prevents infinite loop
    var $form = $('#amount').wrap('<form action="" method="POST">').parent();
    var addr = $('#billing-address').attr('disabled', false).serializeArray();
    $.each(addr, function () {
        $('<input type="hidden">').attr('name', this.name).val(this.value).appendTo($form);
    });
    $form.submit();
};


// Identity
// ========

Liberapay.payments.id = {};

Liberapay.payments.id.submit = function(success) {
    var data = $('#identity').serializeArray();
    jQuery.ajax({
        url: '/'+Liberapay.payments.user_slug+'/identity',
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
    if ($('#bank-account').length === 0) return;
    $('fieldset.tab-pane:not(.active)').prop('disabled', true);
    $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
        $($(e.target).attr('href')).prop('disabled', false);
        $($(e.relatedTarget).attr('href')).prop('disabled', true);
    });
    $('input[inputmode="numeric"]').each(function() {
        var $input = $(this);
        var maxdigits = $input.attr('maxdigits') || $input.attr('digits');
        PaymentCards.restrictNumeric(this, +maxdigits);
    });
};

Liberapay.payments.ba.submit = function () {
    var $ba = $('#bank-account');
    Liberapay.forms.clearInvalid($ba);

    var $iban = $('input[name="IBAN"]');
    var is_iban_invalid = $('#iban').prop('disabled') === false && IBAN.isValid($iban.val()) === false;
    Liberapay.forms.setInvalid($iban, is_iban_invalid);

    var $bban = $('#bban input[name="AccountNumber"]');
    var country = $('#bban select[name="Country"]').val();
    var is_bban_invalid = $('#bban').prop('disabled') === false && IBAN.isValidBBAN(country, $bban.val()) === false;
    Liberapay.forms.setInvalid($bban, is_bban_invalid);

    var invalids = 0;
    $('input[inputmode="numeric"]').each(function() {
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
            Liberapay.forms.setInvalid($input, true);
        } else {
            Liberapay.forms.setInvalid($input, false);
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
        url: '/'+Liberapay.payments.user_slug+'/routes/bank-account.json',
        type: 'POST',
        data: data,
        dataType: 'json',
        success: Liberapay.payments.onSuccess,
        error: Liberapay.payments.error,
    });
};
