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


/* Spinner */
/* ======= */

Gittip.spin = function()
{
    Gittip.disabled = true;
    $('#spinner').show();
};

Gittip.stopSpinning = function()
{
    $('#spinner').hide();
    Gittip.disabled = false;
};


/* Form Generics */
/* ============= */

Gittip.clearFeedback = function()
{
    $('#feedback').empty();
}

Gittip.showFeedback = function(msg, details)
{
    msg = '<h2>' + msg + '</h2>'; 
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
        Gittip.showFeedback("So sorry!!");
        console.log("failed", xhr, foo, bar);
    }

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

Gittip.haveSamurai = false;
Gittip.samuraiAttempts = 0;

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
    Gittip.spin()

    if (!Gittip.haveSamurai)
    {
        if (Gittip.samuraiAttempts++ === 50)
            alert( "Gah! Apparently I don't want your money after all. If "
                 + "you're really motivated, call me (Chad) at 412-925-4220 "
                 + "and we'll figure this out. Sorry. :-("
                  );
        else
            setTimeout(Gittip.submitPaymentForm, 200);
        return false;
    }
    
    function val(field)
    {
        return $('FORM#payment INPUT[name="' + field + '"]').val();
    };

    var data = {};          // top-level POST body

    var pmt = val('payment_method_token');
    if (pmt !== undefined)
        data.payment_method_token = pmt;

    var credit_card = {};   // holds CC info
    credit_card.first_name = val('first_name');
    credit_card.last_name = val('last_name');
    credit_card.address_1 = val('address_1');
    credit_card.address_2 = val('address_2');
    credit_card.city = val('city');
    credit_card.state = val('state');
    credit_card.zip = val('zip');
    credit_card.card_number = val('card_number');
    credit_card.cvv = val('cvv');
    
    var expiry = val('expiry').split('/');
    credit_card.expiry_month = expiry[0];
    credit_card.expiry_year = expiry[1];
    
    data.credit_card = credit_card; 
    Samurai.payment(data, Gittip.savePaymentMethod);

    return false;
};

Gittip.savePaymentMethod = function(data)
{
    // Afaict this is always present, no matter the garbage we gave to Samurai.
    console.log("saving payment method");
    var pmt = data.payment_method.payment_method_token;

    function success()
    {
        $('#status').text('working');
        $('#delete').show();
        Gittip.clearFeedback();
    }

    function detailedFeedback(data)
    {
        $('#status').text('failing');
        $('#delete').show();
        var details = [];
        for (var field in data.errors) 
        {
            var errors = data.errors[field];
            var nerrors = errors.length;
            for (var i=0; i < nerrors; i++)
                details.push(errors[i]);
        }

        Gittip.showFeedback(data.problem, details);
        Gittip.stopSpinning();
    }

    Gittip.submitForm( "/credit-card.json"
                       , {pmt: pmt}
                       , success
                       , detailedFeedback
                        );
};

Gittip.initPayment = function(merchant_key)
{
    $('#delete FORM').submit(Gittip.submitDeleteForm);
    $('FORM#payment').submit(Gittip.submitPaymentForm);
    $('INPUT[name=expiry]').mask('99/2099');

    // Lazily depend on Samurai. 
    var samurai_js = "https://samurai.feefighters.com/assets/api/samurai.js";
    jQuery.getScript(samurai_js, function()
    {
        Samurai.init({merchant_key: merchant_key});
        Gittip.haveSamurai = true;
        console.log("Samurai loaded.");
        console.log($('INPUT').eq(0));
        $('INPUT[type!="hidden"]').eq(0).focus();
    });
};

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
            , data: {amount: amount}
            , type: "GET"
            , error: function(x,y,z) {
                select(cur); console.log(x,y,z);
              }
             }
        );
    });
};
