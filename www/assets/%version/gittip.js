// Degrade the console obj where not present.
// ==========================================
// http://fbug.googlecode.com/svn/branches/firebug1.2/lite/firebugx.js
// Relaxed to allow for Chrome's console.

if (!window.console)
{
    var names = ["log", "debug", "info", "warn", "error", "assert", "dir",
                 "dirxml", "group", "groupEnd", "time", "timeEnd", "count", 
                 "trace", "profile", "profileEnd"];
    window.console = {};
    for (var i=0, name; name = names[i]; i++)
        window.console[name] = function() {};
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
        msg = "Darn it all!";
    msg = '<h3><span class="highlight">' + msg + '</span></h3>'; 
    msg += '<div class="details"></div>';
    $('#feedback').html(msg);
    if (details !== undefined)
        for (var i=0; i < details.length; i++)
            $('#feedback .details').append('<p>' + details[i] + '</p>');
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

    data.csrf = Gittip.getCookie('session');
    jQuery.ajax({ url: url
                , type: "GET"
                , data: data
                , dataType: "json"
                , success: _success
                , error: _error
                 });
}


/* Payment Details Form */
/* ==================== */

Gittip.haveStripe = false;
Gittip.stripeAttempts = 0;

Gittip.submitDeleteForm = function(e)
{
    if (!confirm("Really delete your credit card details?"))
    {
        e.stopPropagation();
        e.preventDefault()
        return false;
    }
};

Gittip.submitPaymentForm = function(e)
{
    e.stopPropagation();
    e.preventDefault();
    $('BUTTON#save').text('Saving ...');
    Gittip.clearFeedback();

    if (!Gittip.haveStripe)
    {
        if (Gittip.stripeAttempts++ === 50)
            alert( "Gah! Apparently we suck. If you're really motivated, call "
                   +"me (Chad) at 412-925-4220 and we'll figure this out. "
                   +"Sorry. :-("
                  );
        else
            setTimeout(Gittip.submitPaymentForm, 200);
        return false;
    }
    

    // Adapt our form lingo to Stripe nomenclature.
    
    function val(field)
    {
        return $('FORM#payment INPUT[id="' + field + '"]').val();
    };

    var credit_card = {};   // holds CC info
    
    credit_card.number = val('card_number');
    console.log(credit_card.number);
    if (credit_card.number.search('[*]') !== -1)
        credit_card.number = '';  // don't send if it's the **** version
    console.log(credit_card.number);
    credit_card.cvc = val('cvv'); // cvv? cvc?
    credit_card.name = val('name');
    credit_card.address_line1 = val('address_1');
    credit_card.address_line2 = val('address_2');
    credit_card.address_state = val('state');
    credit_card.address_zip = val('zip');
    
    var expiry = val('expiry').split('/');  // format enforced by mask
    credit_card.exp_month = expiry[0];
    credit_card.exp_year = expiry[1];


    // Require some options (expiry is theoretically handled by the mask).
    
    if (credit_card.number.match("^[ ]*$") === 0) {
        $('BUTTON#save').text('Save');
        Gittip.showFeedback(null, "Card number is required.");
    } else if (credit_card.cvc.match("[0-9]{3,4}") === -1) {
        $('BUTTON#save').text('Save');
        Gittip.showFeedback(null, "A 3- or 4-digit CVV is required.");
    } else { 
        Stripe.createToken(credit_card, Gittip.stripeResponseHandler);
    }

    return false;
};

Gittip.stripeResponseHandler = function(status, response)
{

    /* Status is guaranteed to be in the set {200,400,401,402,404,500,502,503,
     * 504}. If status === 200 then response.error will contain information 
     * about the error, in this form:
     *
     *      { "code": "incorrect_number"
     *      , "message": "Your card number is incorrect"
     *      , "param": "number"
     *      , "type": "card_error"
     *       }
     *
     * The error codes are documented here:
     *
     *      https://stripe.com/docs/api#errors
     *
     */

    if (status !== 200)
    {   
        $('BUTTON#save').text('Save');
        Gittip.showFeedback(null, [response.error.message]);
    }
    else
    {

        /* The request to create the token succeeded. We now have a single-use
         * token associated with the credit card info. This token can be
         * single-used in one of two ways: to make a charge, or to associate
         * the card with a customer. We want to do the latter, and that happens
         * on the server side. When the card is associated with a customer,
         * Stripe performs card validation, so we will know at that point that
         * the card is good.
         */

        function success()
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
                         , {tok: response.id}
                         , success
                         , detailedFeedback
                          );
    }
};

Gittip.initPayment = function(stripe_publishable_key, participantId)
{
    Gittip.participantId = participantId;
    $('#delete FORM').submit(Gittip.submitDeleteForm);
    $('FORM#payment').submit(Gittip.submitPaymentForm);
    $('INPUT[id=expiry]').mask('99/2099');

    // Lazily depend on Stripe. 
    var stripe_js = "https://js.stripe.com/v1/";
    jQuery.getScript(stripe_js, function()
    {
        Stripe.setPublishableKey(stripe_publishable_key);
        Gittip.haveStripe = true;
        console.log("Stripe loaded.");
        $('INPUT[type!="hidden"]').eq(0).focus();
    });
};

Gittip.getCookie = function(name)
{   // http://www.quirksmode.org/js/cookies.html
    var nameEQ = name + "=";
    var ca = document.cookie.split(';');
    for(var i=0;i < ca.length;i++) {
        var c = ca[i];
        while (c.charAt(0)==' ') c = c.substring(1,c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
    }
    return null;
}

Gittip.initTipButtons = function()
{
    $('BUTTON.tip').click(function()
    {
        var container = $(this).parent();
        function select(btn, amount)
        {
            $('BUTTON.selected', container).removeClass('selected').addClass('empty');
            $(btn).addClass('selected').removeClass('empty');
            if (amount == '0.00')
                $('#payment-prompt.needed').removeClass('needed');
            else
                $('#payment-prompt').addClass('needed');
        }
        var cur = $('BUTTON.selected');
        if (cur.get(0) === this)
        {
            console.log('bail');
            return
        }
        var amount = $(this).text().replace('$', '');
        var tippee = $(this).attr('tippee');
        select(this, amount);
        jQuery.ajax(
            { url: '/' + tippee + '/tip.json'
            , data: {amount: amount, csrf: Gittip.getCookie('session')}
            , type: "POST"
            , error: function(x,y,z) {
                select(cur); console.log(x,y,z);
              }
             }
        );
    });
};


Gittip.initJumpToPerson = function()
{
    function jump(e)
    {
        var val = $('#jump INPUT').val();
        e.preventDefault();
        e.stopPropagation();
        if (val !== '')
            window.location = '/github/' + val + '/';
        return false;
    }
    $('#jump').submit(jump);
}
