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



Lt = {};

Lt.mk = function(tagName)
{
    return $(document.createElement(tagName));
};

Lt.successMessage = function(msg)
{
    Lt.feedback.removeClass('error')
                 .addClass('success')
                 .html(msg)
                 .show();
};

Lt.errorMessage = function(msg)
{
    Lt.feedback.removeClass('success')
                 .addClass('error')
                 .html(msg)
                 .show();
};

Lt.success = function(response)
{
    var problem = response.problem;
    if (problem)
    {
        Lt.errorMessage(problem);
        Lt.enableSubmit();
    }
    else
    {   // On success, force a refresh of the current page. Since we only
        // serve the authentication form on GET, refreshing it will be okay.

        //Lt.successMessage("You are a success!");
        //Lt.enableSubmit();
        window.location.reload(true); // true means 'hard refresh'
    }
};

Lt.error = function(a,b,c)
{
    Lt.errorMessage( "Sorry, a server error prevented us from signing you "
                     + "in. Please try again later.");
    Lt.enableSubmit();
    console.log(a,b,c);
};

Lt.disableSubmit = function()
{
    Lt.submit.attr('disabled', 'true');
    if (Lt.submit.val() === 'Sign In')
        Lt.submit.val('Signing In ...');
    else
        Lt.submit.val('Registering ...');
};

Lt.enableSubmit = function()
{
    Lt.submit.removeAttr('disabled');
    if (Lt.submit.val() === 'Signing In ...')
        Lt.submit.val('Sign In');
    else
        Lt.submit.val('Register');
};

Lt.submitForm = function(e)
{
    e.stopPropagation();
    e.preventDefault();
    Lt.disableSubmit();

    var data = {}
    data.email = $('[name=email]').val();
    data.password = $('[name=password]').val();
    data.confirm = $('[name=confirm]').val();
    jQuery.ajax(
        { url: Lt.form.attr('action')
        , type: "POST"
        , data: data
        , dataType: 'json'
        , success: Lt.success
        , error: Lt.error
         }
    );

    return false;
};

Lt.toggleState = function(e)
{
    e.stopPropagation();
    e.preventDefault();

    Lt.feedback.hide(50);
    if (Lt.other.text() === 'Register')
    {
        Lt.confirmBox.show(100);
        Lt.other.text('Sign In');
        Lt.submit.val('Register');
        Lt.help.show(); 
        Lt.form.attr('action', '/ajax/register.json');
        Lt.first.focus();
    }
    else
    {
        Lt.confirmBox.hide(100);
        Lt.other.text('Register');
        Lt.submit.val('Sign In');
        Lt.help.hide(); 
        Lt.form.attr('action', '/ajax/sign-in.json');
        Lt.first.focus();
    }

    return false;
};

Lt.toggleStateSpace = function(e)
{
    if (e.which === 32)
        Lt.toggleState(e);
};


// Main
// ====

Lt.main = function()
{
    Lt.confirmBox = $('#confirm-box');
    Lt.help = $('LABEL I');
    Lt.feedback = $('#feedback');
    Lt.first = $('.start-here');
    Lt.form = $('FORM');
    Lt.other = $('#other');
    Lt.submit = $('#submit');

    Lt.first.focus();
    Lt.form.submit(Lt.submitForm);
    Lt.other.click(Lt.toggleState);
    Lt.other.keyup(Lt.toggleStateSpace); // capture spacebar too
};

