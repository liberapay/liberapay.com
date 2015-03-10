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

Gratipay.payments.init = function(participantId) {
    Gratipay.participantId = participantId;
    $('#delete form').submit(Gratipay.payments.submitDeleteForm);

    // Lazily depend on Balanced.
    var balanced_js = "https://js.balancedpayments.com/1.1/balanced.min.js";
    jQuery.getScript(balanced_js, function() {
        $('input[type!="hidden"]').eq(0).focus();
    }).fail(Gratipay.error);
}

Gratipay.payments.submitDeleteForm = function(e) {
    var item = $("#payout").length ? "bank account" : "credit card";
    var slug = $("#payout").length ? "bank-account" : "credit-card";
    var msg = "Really disconnect your " + item + "?";
    if (!confirm(msg)) {
        e.stopPropagation();
        e.preventDefault();
        return false;
    }

    jQuery.ajax(
        { url: '/' + slug + '.json'
        , data: {action: "delete"}
        , type: "POST"
        , success: function() {
            window.location.href = '/' + slug + '.html';
          }
        , error: Gratipay.error
         }
    );
    return false;
};

Gratipay.payments.onError = function(response) {
    $('button#save').prop('disabled', false);
    var msg = response.status_code + ": " +
        $.map(response.errors, function(obj) { return obj.description }).join(', ');
    Gratipay.forms.showFeedback(null, [msg]);
    return msg;
};

Gratipay.payments.onSuccess = function(data) {
    $('#status').text('working').addClass('highlight');
    setTimeout(function() {
        $('#status').removeClass('highlight');
    }, 8000);
    $('#delete').show();
    Gratipay.forms.clearFeedback();
    $('button#save').prop('disabled', false);
    setTimeout(function() {
        window.location.href = '/' + Gratipay.participantId + '/';
    }, 1000);
};


// Bank Accounts
// =============

Gratipay.payments.ba = {};

Gratipay.payments.ba.init = function(participantId) {
    Gratipay.payments.init(participantId);
    $('form#bank-account').submit(Gratipay.payments.ba.submit);
};

Gratipay.payments.ba.submit = function (e) {
    e.preventDefault();

    $('button#save').prop('disabled', true);
    Gratipay.forms.clearFeedback();

    var bankAccount = {
        name: $('#account_name').val(),
        account_number: $('#account_number').val(),
        routing_number: $('#routing_number').val()
    };

    var errors = [];


    // Require some fields.
    // ====================

    var requiredFields = {
        account_name: 'The name on your bank account is required.',
        account_number: 'Your bank account number is required.',
        routing_number: 'A routing number is required.'
    };
    for (var field in requiredFields) {
        var $f = $('#' + field);
        if (!$f.length)  // Only validate if it's on the page.
            continue;
        var value = $f.val();

        if (!value) {
            $f.closest('div').addClass('error');
            errors.push(requiredFields[field]);
        } else {
            $f.closest('div').removeClass('error');
        }
    }


    // Validate routing number.
    // ========================

    var $rn = $('#routing_number');
    if (bankAccount.routing_number) {
        if (!balanced.bankAccount.validateRoutingNumber(bankAccount.routing_number)) {
            $rn.closest('div').addClass('error');
            errors.push("That routing number is invalid.");
        } else {
            $rn.closest('div').removeClass('error');
        }
    }


    if (errors.length) {
        $('button#save').prop('disabled', false);
        Gratipay.forms.showFeedback(null, errors);
    } else {
        balanced.bankAccount.create( bankAccount
                                   , Gratipay.payments.ba.handleResponse
                                    );
    }
};

Gratipay.payments.ba.handleResponse = function (response) {
    if (response.status_code !== 201) {
        var msg = Gratipay.payments.onError(response);
        $.post('/bank-account.json', {action: 'store-error', msg: msg});
        return;
    }

    /* The request to tokenize the bank account succeeded. Now we need to
     * validate the merchant information. We'll submit it to
     * /bank-accounts.json and check the response code to see what's going
     * on there.
     */

    function detailedFeedback(data) {
        $('#status').text('failing');
        $('#delete').show();
        var messages = [data.error];
        if (data.problem == 'More Info Needed') {
            messages = [ "Sorry, we couldn't verify your identity. Please "
                       + "check, correct, and resubmit your details."
            ];
        }
        Gratipay.forms.showFeedback(data.problem, messages);
        $('button#save').prop('disabled', false);
    }

    var detailsToSubmit = Gratipay.payments.ba.merchantData;
    detailsToSubmit.bank_account_uri = response.bank_accounts[0].href;

    Gratipay.forms.submit( "/bank-account.json"
                       , detailsToSubmit
                       , Gratipay.payments.onSuccess
                       , detailedFeedback
                        );
};


// Credit Cards
// ============

Gratipay.payments.cc = {};

Gratipay.payments.cc.init = function(participantId) {
    Gratipay.payments.init(participantId);
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
    Gratipay.forms.clearFeedback();

    // Adapt our form lingo to balanced nomenclature.

    function val(field) {
        return $('form#credit-card input[id="' + field + '"]').val();
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

    if (!balanced.card.isCardNumberValid(credit_card.number)) {
        $('button#save').prop('disabled', false);
        Gratipay.forms.showFeedback(null, ["Your card number is bad."]);
    } else if (!balanced.card.isExpiryValid( credit_card.expiration_month
                                         , credit_card.expiration_year
                                          )) {
        $('button#save').prop('disabled', false);
        Gratipay.forms.showFeedback(null, ["Your expiration date is bad."]);
    } else if (!balanced.card.isSecurityCodeValid( credit_card.number
                                               , credit_card.cvv
                                                )) {
        $('button#save').prop('disabled', false);
        Gratipay.forms.showFeedback(null, ["Your CVV is bad."]);
    } else {
        balanced.card.create(credit_card, Gratipay.payments.cc.handleResponse);
    }

    return false;
};

Gratipay.payments.cc.handleResponse = function(response) {
    if (response.status_code !== 201) {
        var msg = Gratipay.payments.onError(response);
        $.post('/credit-card.json', {action: 'store-error', msg: msg});
        return;
    }

    /* The request to create the token succeeded. We now have a single-use
     * token associated with the credit card info. This token can be
     * used to associate the card with a customer. We want to do the
     * latter, and that happens on the server side. When the card is
     * tokenized Balanced performs card validation, so we alredy know the
     * card is good.
     */

    function detailedFeedback(data) {
        $('#status').text('failing');
        $('#delete').show();
        var details = [];
        Gratipay.forms.showFeedback(data.problem, [data.error]);
        $('button#save').prop('disabled', false);
    }

    Gratipay.forms.submit( "/credit-card.json"
                       , {card_uri: response.cards[0].href}
                       , Gratipay.payments.onSuccess
                       , detailedFeedback
                        );
};
