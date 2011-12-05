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


// Add indexOf to IE.
// ==================
// http://stackoverflow.com/questions/1744310/how-to-fix-array-indexof-in-javascript-for-ie-browsers

if (!Array.prototype.indexOf)
{
    Array.prototype.indexOf = function(obj, start)
    {
         for (var i = (start || 0), j = this.length; i < j; i++)
             if (this[i] == obj)
                return i;
         return -1;
    }
}


// Main Namespace
// ==============

Anon = {};

Anon.create = function(tagName)
{
    return $(document.createElement(tagName));
};

Anon.resize = function()
{
    var formHeight = 386; // hard-coded, because 1 in 30 times I am seeing
                          // the form box pushed way down (cross-browser)
    var topPad = ($(window).height() - formHeight) / 2;
    $('BODY').css('padding-top', topPad);
};

Anon.successMessage = function(msg)
{
    $('#feedback').removeClass('error')
                  .addClass('success')
                  .html(msg)
                  .show();
};

Anon.errorMessage = function(msg)
{
    $('#feedback').removeClass('success')
                  .addClass('error')
                  .html(msg)
                  .show();
};

Anon.success = function(info)
{
    console.log(info);
    if (!info)
    {
        Anon.errorMessage( "Sorry, those credentials are invalid.");
        Anon.enableSubmit();
    }
    else
    {   // On success, force a refresh of the current page. Since we only
        // serve the authentication form on GET, refreshing it will be okay.

        //Anon.successMessage("You are a success!");
        //Anon.enableSubmit();
        window.location.reload(true); // true means 'hard refresh'
    }
};

Anon.error = function(a,b,c)
{
    Anon.errorMessage( "Sorry, a server error prevented us from logging you "
                     + "in. Please try again later.");
    Anon.enableSubmit();
    console.log(a,b,c);
};

Anon.disableSubmit = function()
{
    $('#submit').attr('disabled', 'true');
    $('#submit').val('Logging in ...');
};

Anon.enableSubmit = function()
{
    $('#submit').removeAttr('disabled');
    $('#submit').val('Login');
};

Anon.authenticate = function()
{
    Anon.disableSubmit(); 
    var data = {}
    data.email = $('[name=email]').val();
    data.password = $('[name=password]').val();
    jQuery.ajax(
        { url: $('FORM').attr('action')
        , type: "POST"
        , data: data
        , dataType: 'json'
        , success: Anon.success
        , error: Anon.error
         }
    );
    return false;
};


// Main
// ====

Anon.main = function()
{
    Anon.resize()
    $(window).resize(Anon.resize);
    $('.start-here').focus();
    $('FORM').submit(Anon.authenticate);
};
