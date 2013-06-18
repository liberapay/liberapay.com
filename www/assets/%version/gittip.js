// Degrade the console obj where not present.
// ==========================================
// http://fbug.googlecode.com/svn/branches/firebug1.2/lite/firebugx.js
// Relaxed to allow for Chrome's console.

function mock_console()
{
    var names = ["log", "debug", "info", "warn", "error", "assert", "dir",
                 "dirxml", "group", "groupEnd", "time", "timeEnd", "count",
                 "trace", "profile", "profileEnd"];
    window.console = {};
    for (var i=0, name; name = names[i]; i++)
        window.console[name] = function() {};
}

if (!window.console)
{
    mock_console();
}


// Make sure we have some things.
// ==============================

$.fn.serializeObject = function()
{   // http://stackoverflow.com/questions/763345/jquery-how-to-store-form-values-in-data-object
    var o = {};
    var a = this.serializeArray();
    $.each(a, function() {
        if (o[this.name] !== undefined) {
            if (!o[this.name].push) {
                o[this.name] = [o[this.name]];
            }
            o[this.name].push(this.value || '');
        } else {
            o[this.name] = this.value || '';
        }
    });
    return o;
};

if (!Array.prototype.indexOf)
{   // http://stackoverflow.com/questions/1744310/how-to-fix-array-indexof-in-javascript-for-ie-browsers
    Array.prototype.indexOf = function(obj, start)
    {
         for (var i = (start || 0), j = this.length; i < j; i++)
             if (this[i] == obj)
                return i;
         return -1;
    }
}

if (!String.prototype.replaceAll)
{
    String.prototype.replaceAll = function(p, r)
    {
        var s = this;
        while (s.indexOf(p) !== -1)
            s = s.replace(p, r);
        return s;
    }
}

if(!String.prototype.trim)
{   // http://stackoverflow.com/questions/1418050/string-strip-for-javascript
    String.prototype.trim = function()
    {
        return String(this).replace(/^\s+|\s+$/g, '');
    };
}

if(!Array.prototype.remove)
{   //http://ejohn.org/blog/javascript-array-remove/
    Array.prototype.remove = function(from, to)
    {
        var rest = this.slice((to || from) + 1 || this.length);
        this.length = from < 0 ? this.length + from : from;
        return this.push.apply(this, rest);
    }
};

function prettyDate(time) {
    // http://ejohn.org/blog/javascript-pretty-date/
    var munged = (time || "").replace(/-\d\d:\d\d$/,"")
                             .replace(/-/g,"/")
                             .replace(/[TZ]/g," "),
        date = new Date(munged),
        diff = (((new Date()).getTime() - date.getTime()) / 1000),
        day_diff = Math.floor(diff / 86400);
    console.log(time, munged, date, diff, day_diff);
    if ( isNaN(day_diff) || day_diff < 0 || day_diff >= 31 )
        return;

    return day_diff == 0 && (
            diff < 60 && "just now" ||
            diff < 120 && "1 minute" ||
            diff < 3600 && Math.floor( diff / 60 ) + " minutes" ||
            diff < 7200 && "1 hour" ||
            diff < 86400 && Math.floor( diff / 3600 ) + " hours") ||
        day_diff == 1 && "Yesterday" ||
        day_diff < 7 && day_diff + " days" ||
        day_diff < 31 && Math.ceil( day_diff / 7 ) + " weeks";
}

// Main namespace.
// ===============

Gittip = {};


/* Form Generics */
/* ============= */

Gittip.clearFeedback = function()
{
    $('#feedback').empty();
}

Gittip.showFeedback = function(msg, details)
{
    if (msg === null)
        msg = "Failure";
    msg = '<h2><span class="highlight">' + msg + '</span></h2>';
    msg += '<ul class="details"></ul>';
    $('#feedback').html(msg);
    if (details !== undefined)
        for (var i=0; i < details.length; i++)
            $('#feedback .details').append('<li>' + details[i] + '</li>');
}

Gittip.submitForm = function(url, data, success, error)
{
    if (success === undefined)
    {
        success = function()
        {
            Gittip.showFeedback("Success!");
        }
    }

    if (error === undefined)
    {
        error = function(data)
        {
            Gittip.showFeedback(data.problem);
        };
    }

    function _success(data)
    {
        if (data.problem === "" || data.problem === undefined)
            success(data);
        else
            error(data);
    }

    function _error(xhr, foo, bar)
    {
        Gittip.showFeedback( "So sorry!!"
                           , ["There was a fairly drastic error with your "
                             +"request."]
                            );
        console.log("failed", xhr, foo, bar);
    }

    jQuery.ajax({ url: url
                , type: "POST"
                , data: data
                , dataType: "json"
                , success: _success
                , error: _error
                 });
}


/* Payment Details Form */
/* ==================== */

Gittip.havePayments = false;
Gittip.paymentProcessorAttempts = 0;

Gittip.submitDeleteForm = function(e)
{
    var item = $("#payout").length ? "bank account" : "credit card";
    var slug = $("#payout").length ? "bank-account" : "credit-card";
    var msg = "Really disconnect your " + item + "?";
    if (!confirm(msg))
    {
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
        , error: function(x,y,z) {
            select(cur);
            alert("Sorry, something went wrong deleting your " + item + ". :(");
            console.log(x,y,z);
          }
         }
    );
    return false;
};

Gittip.submitPayoutForm = function (e) {
    e.preventDefault();

    $('BUTTON#save').text('Saving ...');
    Gittip.clearFeedback();

    var bankAccount = {
        name: $('#account_name').val(),
        account_number: $('#account_number').val(),
        bank_code: $('#routing_number').val()
    };

    var dobs = [
        $('#dob-year').val(),
        $('#dob-month').val(),
        $('#dob-day').val()
    ];

    Gittip.merchantData = {
        type: 'person',  // Oooh, may need to vary this some day?
        street_address: $('#address_1').val(),
        postal_code: $('#zip').val(),
        phone_number: $('#phone_number').val(),
        region: $('#state').val(),
        dob: dobs.join('-'),
        name: $('#name').val()
    };
    var errors = [];


    // Require some fields.
    // ====================
    // We only require fields that are actually on the page. Since we don't
    // load the identity verification fields if they're already verified, not
    // all of these will necessarily be present at all.

    var requiredFields = {
        name: 'Your legal name is required.',
        address_1: 'Your street address is required.',
        zip: 'Your ZIP or postal code is required.',
        phone_number: 'A phone number is required.',
        account_name: 'The name on your bank account is required.',
        account_number: 'Your bank account number is required.',
        routing_number: 'A routing number is required.'
    };
    for (var field in requiredFields)
    {
        var $f = $('#' + field);
        if (!$f.length)  // Only validate if it's on the page.
            continue;
        var value = $f.val();

        if (!value)
        {
            $f.closest('div').addClass('error');
            errors.push(requiredFields[field]);
        }
        else
        {
            $f.closest('div').removeClass('error');
        }
    }


    // Validate date of birth.
    // =======================
    // This might not be on the page if they've already verified their
    // identity.

    if (dobs[0] !== undefined)
    {
        var d = new Date(dobs[0], dobs[1] - 1, dobs[2]);
        // (1900, 2, 31) gives 3 march :P
        if (d.getMonth() !== dobs[1] - 1)
            errors.push('Invalid date of birth.');
    }


    // Validate routing number.
    // ========================

    var $rn = $('#routing_number');
    if (bankAccount.bank_code)
    {
        if (!balanced.bankAccount.validateRoutingNumber(bankAccount.bank_code))
        {
            $rn.closest('div').addClass('error');
            errors.push("That routing number is invalid.");
        }
        else
        {
            $rn.closest('div').removeClass('error');
        }
    }


    if (errors.length)
    {
        $('BUTTON#save').text('Save');
        Gittip.showFeedback(null, errors);
    }
    else
    {
        balanced.bankAccount.create(bankAccount, Gittip.bankAccountResponseHandler);
    }
};

Gittip.bankAccountResponseHandler = function (response) {
    console.log('bank account response', response);
    if (response.status != 201)
    {
        $('BUTTON#save').text('Save');
        var msg = response.status.toString() + " " + response.error.description;
        jQuery.ajax(
            { type: "POST"
            , url: "/bank-account.json"
            , data: {action: 'store-error', msg: msg}
             }
        );

        Gittip.showFeedback(null, [response.error.description]);
    }
    else
    {

        /* The request to tokenize the bank account succeeded. Now we need to
         * validate the merchant information. We'll submit it to
         * /bank-accounts.json and check the response code to see what's going
         * on there.
         */

        function success()
        {
            $('#status').text('connected').addClass('highlight');
            setTimeout(function() {
                $('#status').removeClass('highlight');
            }, 8000);
            $('#delete').show();
            Gittip.clearFeedback();
            $('BUTTON#save').text('Save');
            setTimeout(function() {
                window.location.href = '/' + Gittip.participantId + '/';
            }, 1000);
        }

        function detailedFeedback(data)
        {
            $('#status').text('failing');
            $('#delete').show();
            var messages = [data.error];
            if (data.problem == 'More Info Needed') {
                var redirect_uri = data.redirect_uri;
                for (var key in Gittip.merchantData) {
                    redirect_uri += 'merchant[' + encodeURIComponent(key) + ']'
                        + '=' + encodeURIComponent((Gittip.merchantData[key])) + '&';
                }
                messages = [ "Sorry, we couldn't verify your identity. Please "
                           + "check, correct, and resubmit your details, or "
                           + "step through our <a href=\"" + redirect_uri
                           + "\">payment processor's escalation process</a>."
                ];
            }
            Gittip.showFeedback(data.problem, messages);
            $('BUTTON#save').text('Save');
        }

        var detailsToSubmit = Gittip.merchantData;
        detailsToSubmit.bank_account_uri = response.data.uri;

        Gittip.submitForm( "/bank-account.json"
                         , detailsToSubmit
                         , success
                         , detailedFeedback
                          );
    }
};

Gittip.submitPaymentForm = function(e)
{

    e.stopPropagation();
    e.preventDefault();
    $('BUTTON#save').text('Saving ...');
    Gittip.clearFeedback();

    if (!Gittip.havePayments)
    {
        if (Gittip.paymentProcessorAttempts++ === 50)
            alert( "Gah! Apparently we suck. If you're really motivated, call "
                   +"me (Chad) at 412-925-4220 and we'll figure this out. "
                   +"Sorry. :-("
                  );
        else
            setTimeout(Gittip.submitPaymentForm, 200);
        return false;
    }


    // Adapt our form lingo to balanced nomenclature.

    function val(field)
    {
        return $('FORM#payment INPUT[id="' + field + '"]').val();
    }

    var credit_card = {};   // holds CC info

    credit_card.card_number = val('card_number');
    if (credit_card.card_number.search('[*]') !== -1)
        credit_card.card_number = '';  // don't send if it's the **** version
    credit_card.security_code = val('cvv');
    credit_card.name = val('name');
    credit_card.street_address = val('address_1');
    credit_card.region = val('state');
    country = $('select[id="country"]').val();
    credit_card.meta = { 'address_2': val('address_2')
                       , 'region': credit_card.region // workaround
                       , 'city_town': val('city_town')
                       , 'country': country
                        };

    credit_card.postal_code = val('zip');

    credit_card.expiration_month = val('expiration_month');
    credit_card.expiration_year = val('expiration_year');

    if (!balanced.card.isCardNumberValid(credit_card.card_number))
    {
        $('BUTTON#save').text('Save');
        Gittip.showFeedback(null, ["Your card number is bad."]);
    }
    else if (!balanced.card.isExpiryValid( credit_card.expiration_month
                                         , credit_card.expiration_year
                                          ))
    {
        $('BUTTON#save').text('Save');
        Gittip.showFeedback(null, ["Your expiration date is bad."]);
    }
    else if (!balanced.card.isSecurityCodeValid( credit_card.card_number
                                               , credit_card.security_code
                                                ))
    {
        $('BUTTON#save').text('Save');
        Gittip.showFeedback(null, ["Your CVV is bad."]);
    }
    else
    {
        balanced.card.create(credit_card, Gittip.paymentsResponseHandler);
    }

    return false;
};

Gittip.paymentsResponseHandler = function(response)
{

    /* If status !== 201 then response.error will contain information about the
     * error, in this form:
     *
     *      { "code": "incorrect_number"
     *      , "message": "Your card number is incorrect"
     *      , "param": "number"
     *      , "type": "card_error"
     *       }
     *
     * The error codes are documented here:
     *
     *      https://www.balancedpayments.com/docs/js
     *
     */

    if (response.status !== 201)
    {   // The request to create the token failed. Store the failure message in
        // our db.
        $('BUTTON#save').text('Save');
        var msg = response.status.toString() + " " + response.error.description;
        jQuery.ajax(
            { type: "POST"
            , url: "/credit-card.json"
            , data: {action: 'store-error', msg: msg}
             }
        );

        Gittip.showFeedback(null, [response.error.description]);
    }
    else
    {

        /* The request to create the token succeeded. We now have a single-use
         * token associated with the credit card info. This token can be
         * used to associate the card with a customer. We want to do the
         * latter, and that happens on the server side. When the card is
         * tokenized Balanced performs card validation, so we alredy know the
         * card is good.
         */

        function success(data)
        {
            $('#status').text('working').addClass('highlight');
            setTimeout(function() {
                $('#status').removeClass('highlight');
            }, 8000);
            $('#delete').show();
            Gittip.clearFeedback();
            $('BUTTON#save').text('Save');
            setTimeout(function() {
                window.location.href = '/' + Gittip.participantId + '/';
            }, 1000);

            // Log to mixpanel.
            if (data.first_time === true)
                mixpanel.track("Add Credit Card");
        }

        function detailedFeedback(data)
        {
            $('#status').text('failing');
            $('#delete').show();
            var details = [];
            Gittip.showFeedback(data.problem, [data.error]);
            $('BUTTON#save').text('Save');
        }

        Gittip.submitForm( "/credit-card.json"
                         , {card_uri: response.data.uri}
                         , success
                         , detailedFeedback
                          );
    }
};

Gittip.initPayment = function(balanced_uri, participantId)
{
    Gittip.participantId = participantId;
    $('#delete FORM').submit(Gittip.submitDeleteForm);
    $('FORM#payment').submit(Gittip.submitPaymentForm);

    // Lazily depend on Balanced.
    var balanced_js = "https://js.balancedpayments.com/v1/balanced.js";
    jQuery.getScript(balanced_js, function()
    {
        balanced.init(balanced_uri);
        Gittip.havePayments = true;
        $('INPUT[type!="hidden"]').eq(0).focus();
    });
};

Gittip.initPayout = function(balanced_uri, participantId)
{
    Gittip.participantId = participantId;
    $('#delete FORM').submit(Gittip.submitDeleteForm);
    $('#payout').submit(Gittip.submitPayoutForm);

    // Lazily depend on Balanced.
    var balanced_js = "https://js.balancedpayments.com/v1/balanced.js";
    jQuery.getScript(balanced_js, function()
    {
        balanced.init(balanced_uri);
        Gittip.havePayouts = true;
        $('INPUT[type!="hidden"]').eq(0).focus();
    });
};

Gittip.getCookie = function(name)
{
    var cookieValue = null;
    if (document.cookie && document.cookie != '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) == (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
};

Gittip.initCSRF = function()
{   // https://docs.djangoproject.com/en/dev/ref/contrib/csrf/#ajax
    jQuery(document).ajaxSend(function(event, xhr, settings) {
        function sameOrigin(url) {
            // url could be relative or scheme relative or absolute
            var host = document.location.host; // host + port
            var protocol = document.location.protocol;
            var sr_origin = '//' + host;
            var origin = protocol + sr_origin;
            // Allow absolute or scheme relative URLs to same origin
            return (url == origin || url.slice(0, origin.length + 1) == origin + '/') ||
                (url == sr_origin || url.slice(0, sr_origin.length + 1) == sr_origin + '/') ||
                // or any other URL that isn't scheme relative or absolute i.e relative.
                !(/^(\/\/|http:|https:).*/.test(url));
        }
        function safeMethod(method) {
            return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
        }

        if (!safeMethod(settings.type) && sameOrigin(settings.url)) {
            xhr.setRequestHeader( "X-CSRF-TOKEN"
                                , Gittip.getCookie('csrf_token')
                                 );
        }
    });
};

Gittip.initTipButtons = function()
{
    // For authenticated users we change the tip!

    $('INPUT.my-tip:not(.anon)').change(function()
    {
        // Define a closure that will be used to show/hide the payment prompt.

        function changePaymentPrompt(amount)
        {
            if (amount === '0.00')
                $('#payment-prompt.needed').removeClass('needed');
            else
                $('#payment-prompt').addClass('needed');
        }


        // Go to work!

        var amount = $(this).val();
        var oldAmount = $(this).attr('data-old-amount');
        var tippee = $(this).attr('data-tippee');

        if (oldAmount === amount)
            return;

        changePaymentPrompt(amount);

        jQuery.ajax(
            { url: '/' + tippee + '/tip.json'
            , data: {amount: amount}
            , type: "POST"
            , error: function(x,y,z) {
                changePaymentPrompt(oldAmount);
                alert("Sorry, something went wrong changing your tip. :(");
                console.log(x,y,z);
              }
             }
        )
        .done(function(data) {
            $('.total-giving').text(data['total_giving']);

            // Log to mixpanel.
            if (data.first_time === true)
                mixpanel.track("Explicitly Tip");
        });
    });


    // Range

    $('.my-tip-range INPUT.my-tip').each(function() {
        var drag     = false,
            delta    = 0,
            $gift    = $(this),
            $parent  = $gift.parent(),
            $zero    = $('<button>$0</button>'),
            $quarter = $('<button>25¢</button>'),
            $handle  = $('<button class="my-tip-range-handle">$10</button>'),
            $range   = $('<div class="my-tip-range-range"/>');

        function xMax() {
            return $range.innerWidth() -
                     parseInt($range.css('padding-left'), 10) -
                     parseInt($range.css('padding-right'), 10) -
                   $handle.outerWidth() -
                     parseInt($handle.css('margin-left'), 10) -
                     parseInt($handle.css('margin-right'), 10);
        }

        $handle.css({
            position: 'relative',
            left: 0
        });

        $range.css({
            position: 'relative',
            display: 'inline-block'
        });

        $handle.on({
            'mousedown touchstart': function(e) {
                var clientX = e.originalEvent.touches ? e.originalEvent.touches[0].clientX : e.clientX;
                drag = true;
                delta = clientX - parseInt($handle.css('left'), 10);
                $parent.find('button').removeClass('selected');
                $handle.addClass('selected drag');
                $gift.val($handle.text().substr(1));
            }
        });

        $(window).on({
            'mousemove touchmove': function(e) {
                if (!drag) return;

                var value,
                    clientX = e.originalEvent.touches ? e.originalEvent.touches[0].clientX : e.clientX,
                    x   = clientX - delta,
                    max = xMax();

                if (x < 0)   x = 0;
                if (x > max) x = max;

                value = Math.round(x / max * 99) + 1;

                $handle
                    .text('$' + value)
                    .css('left', x);

                $gift.val(value);
            },

           'mouseup touchend': function() {
                if (!drag) return;
                drag = false;
                $gift.trigger('change');
                $handle.removeClass('drag');
            }
        });

        $zero.click(function() {
            $gift.val(0).trigger('change');
            $parent.find('button').removeClass('selected');
            $zero.addClass('selected');
        });

        $quarter.click(function() {
            $gift.val(0.25).trigger('change');
            $parent.find('button').removeClass('selected');
            $quarter.addClass('selected');
        });

        $range.append($handle);
        $parent.append($zero, $quarter, $range);

        // init
        $handle.css('left', (+$handle.text().substr(1) / 100) * xMax());

        switch (+$gift.val()) {
            case 0: $zero.addClass('selected'); break;
            case 0.25: $quarter.addClass('selected'); break;
            default:
                $handle.text("$" + (+$gift.val()));
                $handle.css('left', (+$gift.val() / 100) * xMax());
                $handle.addClass('selected');
                break;
        }
    });


    // For anonymous users we flash a login link.

    $('.my-tip-range.anon BUTTON').mouseover(
        function() { $('.nav.level-1 .flash-me').addClass('highlight'); }
    );
    $('.my-tip-range.anon BUTTON').click(function()
    {
        var i = 0
        function flash()
        {
            if (i++ == 6) return;
            $('.nav.level-1 .flash-me').toggleClass('highlight');
            setTimeout(flash, 100);
        }
        flash();
    });
};


Gittip.initJumpToPerson = function()
{
    function jump(e)
    {
        var platform = $('#jump SELECT').val().trim();
        var val = $('#jump INPUT').val().trim();
        e.preventDefault();
        e.stopPropagation();
        if (val !== '')
            window.location = '/on/' + platform + '/' + val + '/';
        return false;
    }
    $('#jump').submit(jump);
}


// Communities
// ===========

Gittip.communities = {};

Gittip.communities.update = function(name, is_member, callback)
{
    jQuery.ajax(
        { type: 'POST'
        , url: '/for/communities.json'
        , data: {name: name, is_member: is_member}
        , dataType: 'json'
        , success: callback
         }
    );
}

Gittip.communities.jumpTo = function(slug)
{
    window.location.href = "/for/" + slug + "/";
};

Gittip.communities.join = function(name, callback)
{
    Gittip.communities.update(name, true, callback);
};

Gittip.communities.leave = function(name, callback)
{
    if (confirm("Are you sure you want to leave the " + name + " community?"))
        Gittip.communities.update(name, false, callback);

}


// Horns
// =====

Gittip.horn = {};

Gittip.horn.init = function()
{
    Gittip.horn.since_id = undefined;
    $('#toot-form').submit(Gittip.horn.toot);
    Gittip.horn.update({limit: 20});
};

Gittip.horn.update = function(data)
{
    clearTimeout(Gittip.horn.handle);
    data = data || {};
    if (Gittip.horn.since_id !== undefined)
        data.since_id = Gittip.horn.since_id;
    jQuery.ajax(
        { type: "GET"
        , url: "toots.json"
        , data: data
        , success: Gittip.horn.draw
         });
};

Gittip.horn.draw = function(toots)
{
    for (var i=toots.length-1, toot; toot = toots[i]; i--)
    {
        Gittip.horn.since_id = toot.id;
        Gittip.horn.drawOne(toot);
    }
    Gittip.horn.handle = setTimeout(Gittip.horn.update, 1000)
};

Gittip.horn.drawOne = function(toot)
{
    var escaped = $('<div>').text(toot.toot).html();
    var html = '<li class="'
             + (toot.horn === toot.tootee ? 'me' : 'them')
             + ' '
             + (toot.own ? 'own' : 'theirs')
             + '"><span class="toot">'
             + ( toot.tootee !== toot.horn && !toot.own
               ? 're: ' + toot.tootee + ': '
               : ''
                )
             + escaped
             + ( toot.tootee !== toot.horn && toot.own
               ? '&mdash;' + toot.tootee
               : ''
                )
             + '</div>'
             + '</span>'
             + '</li>'
    $('#toots').prepend(html)
};

Gittip.horn.success = function(data)
{
    // clear the textarea & draw any new toots
    $('#toot').val('');
    Gittip.horn.update(data);
};

Gittip.horn.toot = function(e)
{
    e.preventDefault();
    e.stopPropagation();
    var toot = $('#toot').val();

    jQuery.ajax(
        { type: "POST"
        , url: "toot.json"
        , data: {toot: toot}
        , success: Gittip.horn.success
         });
    return false;
};
