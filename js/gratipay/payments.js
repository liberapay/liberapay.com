/* Bank Account and Credit Card forms
 *
 * These two forms share some common wiring under the Gratipay.payments
 * namespace, and each has unique code under the Gratipay.payments.{cc,ba}
 * namespaces. Each form gets its own page so we only instantiate one of these
 * at a time.
 *
 */

Gratipay.payments = {};


// Common code
// ===========

Gratipay.payments.init = function() {
    $('#delete').submit(Gratipay.payments.deleteRoute);

    // Lazily depend on Balanced.
    var balanced_js = "https://js.balancedpayments.com/1.1/balanced.min.js";
    jQuery.getScript(balanced_js, function() {
        $('input[type!="hidden"]').eq(0).focus();
    }).fail(Gratipay.error);
}

Gratipay.payments.deleteRoute = function(e) {
    e.stopPropagation();
    e.preventDefault();

    var $this = $(this);
    var confirm_msg = $this.data('confirm');
    if (confirm_msg && !confirm(confirm_msg)) {
        return false;
    }
    jQuery.ajax(
        { url: "/" + Gratipay.username + "/routes/delete.json"
        , data: {network: $this.data('network'), address: $this.data('address')}
        , type: "POST"
        , success: function() { window.location.reload(); }
        , error: Gratipay.error
         }
    );
    return false;
};

Gratipay.payments.onError = function(response) {
    $('button#save').prop('disabled', false);
    var msg = response.status_code + ": " +
        $.map(response.errors, function(obj) { return obj.description }).join(', ');
    Gratipay.notification(msg, 'error', -1);
    return msg;
};

Gratipay.payments.onSuccess = function(data) {
    $('button#save').prop('disabled', false);
    window.location.reload();
};

Gratipay.payments.associate = function (network) { return function (response) {
    if (response.status_code !== 201) {
        return Gratipay.payments.onError(response);
    }

    /* The request to tokenize the thing succeeded. Now we need to associate it
     * to the Customer on Balanced and to the participant in our DB.
     */
    var data = {
        network: network,
        address: network == 'balanced-ba' ? response.bank_accounts[0].href
                                          : response.cards[0].href,
    };

    jQuery.ajax({
        url: "associate.json",
        type: "POST",
        data: data,
        dataType: "json",
        success: Gratipay.payments.onSuccess,
        error: [
            Gratipay.error,
            function() { $('button#save').prop('disabled', false); },
        ],
    });
}};


// Bank Accounts
// =============

Gratipay.payments.ba = {};

Gratipay.payments.ba.init = function() {
    Gratipay.payments.init();
    $('form#bank-account').submit(Gratipay.payments.ba.submit);
};

Gratipay.payments.ba.submit = function (e) {
    e.preventDefault();

    $('button#save').prop('disabled', true);
    Gratipay.forms.clearInvalid($(this));

    var bankAccount = {
        name: $('#account_name').val(),
        account_number: $('#account_number').val(),
        routing_number: $('#routing_number').val()
    };

    // Validate routing number.
    if (bankAccount.routing_number) {
        if (!balanced.bankAccount.validateRoutingNumber(bankAccount.routing_number)) {
            Gratipay.forms.setInvalid($('#routing_number'));
            Gratipay.forms.focusInvalid($(this));
            $('button#save').prop('disabled', false);
            return false
        }
    }

    // Okay, send the data to Balanced.
    balanced.bankAccount.create( bankAccount
                               , Gratipay.payments.associate('balanced-ba')
                                );
};


// Credit Cards
// ============

Gratipay.payments.cc = {};

Gratipay.payments.cc.init = function() {
    Gratipay.payments.init();
    $('form#credit-card').submit(Gratipay.payments.cc.submit);
    Gratipay.payments.cc.formatInputs(
        $('#card_number'),
        $('#expiration_month'),
        $('#expiration_year'),
        $('#cvv')
    );
};


/* Most of the following code is taken from https://github.com/wangjohn/creditly */

Gratipay.payments.cc.formatInputs = function (cardNumberInput, expirationMonthInput, expirationYearInput, cvvInput) {
    function getInputValue(e, element) {
        var inputValue = element.val().trim();
        inputValue = inputValue + String.fromCharCode(e.which);
        return inputValue.replace(/[^\d]/g, "");
    }

    function isEscapedKeyStroke(e) {
        // Key event is for a browser shortcut
        if (e.metaKey || e.ctrlKey) return true;

        // If keycode is a space
        if (e.which === 32) return false;

        // If keycode is a special char (WebKit)
        if (e.which === 0) return true;

        // If char is a special char (Firefox)
        if (e.which < 33) return true;

        return false;
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

    function addSpaces(number, spaces) {
      var parts = []
      var j = 0;
      for (var i=0; i<spaces.length; i++) {
        if (number.length > spaces[i]) {
          parts.push(number.slice(j, spaces[i]));
          j = spaces[i];
        } else {
          if (i < spaces.length) {
            parts.push(number.slice(j, spaces[i]));
          } else {
            parts.push(number.slice(j));
          }
          break;
        }
      }

      if (parts.length > 0) {
        return parts.join(" ");
      } else {
        return number;
      }
    }

    var americanExpressSpaces = [4, 10, 15];
    var defaultSpaces = [4, 8, 12, 16];

    cardNumberInput.on("keypress", function(e) {
        var number = getInputValue(e, cardNumberInput);
        var isAmericanExpressCard = isAmericanExpress(number);
        var maximumLength = (isAmericanExpressCard ? 15 : 16);
        if (shouldProcessInput(e, maximumLength, cardNumberInput)) {
            var newInput;
            newInput = isAmericanExpressCard ? addSpaces(number, americanExpressSpaces) : addSpaces(number, defaultSpaces);
            cardNumberInput.val(newInput);
        }
    });

    expirationMonthInput.on("keypress", function(e) {
        var maximumLength = 2;
        if (shouldProcessInput(e, maximumLength, expirationMonthInput)) {
            var newInput = getInputValue(e, expirationMonthInput);
            if (newInput < 13) {
                expirationMonthInput.val(newInput);
            } else {
                e.preventDefault();
            }
        }
    });

    expirationYearInput.on("keypress", function(e) {
        var maximumLength = 2;
        if (shouldProcessInput(e, maximumLength, expirationYearInput)) {
            var newInput = getInputValue(e, expirationYearInput);
            expirationYearInput.val(newInput);
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

Gratipay.payments.cc.submit = function(e) {

    e.stopPropagation();
    e.preventDefault();
    $('button#save').prop('disabled', true);
    Gratipay.forms.clearInvalid($(this));

    // Adapt our form lingo to balanced nomenclature.

    function val(field) {
        return $('form#credit-card #'+field).val();
    }

    var credit_card = {};   // holds CC info

    credit_card.number = val('card_number').replace(/[^\d]/g, '');
    credit_card.cvv = val('cvv');
    credit_card.name = val('name');
    var country = val('country') || null;

    credit_card.meta = { 'address_2': val('address_2')
                       , 'region': val('state')
                       , 'city_town': val('city_town')
                       , 'country': country
                        };

    // XXX We're duping some of this info in both meta and address due to
    // evolution of the Balanced API and our stepwise keeping-up. See:
    // https://github.com/gratipay/gratipay.com/issues/2446 and links from
    // there.
    credit_card.address = { 'line1': val('address_1')
                          , 'line2': val('address_2')
                          , 'city': val('city_town')
                          , 'state': val('state')
                          , 'postal_code': val('zip')
                          , 'country_code': country
                           };

    credit_card.expiration_month = val('expiration_month');
    var year = val('expiration_year');
    credit_card.expiration_year = year.length == 2 ? '20' + year : year;

    var is_card_number_invalid = !balanced.card.isCardNumberValid(credit_card.number);
    var is_expiry_invalid = !balanced.card.isExpiryValid(credit_card.expiration_month,
                                                         credit_card.expiration_year);
    var is_cvv_invalid = !balanced.card.isSecurityCodeValid(credit_card.number,
                                                            credit_card.cvv);

    Gratipay.forms.setInvalid($('#card_number'), is_card_number_invalid);
    Gratipay.forms.setInvalid($('#expiration_month'), is_expiry_invalid);
    Gratipay.forms.setInvalid($('#cvv'), is_cvv_invalid);

    if (is_card_number_invalid || is_expiry_invalid || is_cvv_invalid) {
        $('button#save').prop('disabled', false);
        Gratipay.forms.focusInvalid($(this));
        return false;
    }

    balanced.card.create(credit_card, Gratipay.payments.associate('balanced-cc'));
    return false;
};
