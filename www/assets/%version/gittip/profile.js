Gittip.profile = {};

Gittip.profile.toNumber = function(number)
{
    if (number == 'plural')
        Gittip.profile.toPlural();
    else if (number == 'singular')
        Gittip.profile.toSingular();
};

Gittip.profile.toPlural = function()
{
    $('.i-am').text('We are');
    $('.i-m').text("We're");
    $('.my').text("Our");
};

Gittip.profile.toSingular = function()
{
    $('.i-am').text('I am');
    $('.i-m').text("I'm");
    $('.my').text("My");
};

$(document).ready(function()
{

    ////////////////////////////////////////////////////////////
    //                                                         /
    // XXX This is ripe for refactoring. I ran out of steam. :-/
    //                                                         /
    ////////////////////////////////////////////////////////////


    // Wire up username knob.
    // ======================

    $('FORM.username BUTTON.edit').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        $('.username BUTTON.edit').hide();
        $('.username BUTTON.save').show();
        $('.username BUTTON.cancel').show();
        $('.username SPAN.view').hide();
        $('.username INPUT').show().focus();
        $('.username .warning').show();
        return false;
    });
    $('FORM.username').submit(function(e)
    {
        e.preventDefault();

        $('#save-username').text('Saving ...');

        var username = $('INPUT[name=username]').val();

        function success(d)
        {
            window.location.href = "/" + encodeURIComponent(d.username) + "/";
        }
        function error(e)
        {
            $('#save-username').text('Save');
            if (e.status === 409)
            {
                alert("Sorry, that username is already taken.");
            }
            else if (e.status === 413)
            {
                alert( "Sorry, that username is too long (it can only "
                     + "have 32 characters).");
            }
            else
            {
                alert( "Sorry, something went wrong. Either you used "
                     + "disallowed characters or something broke on "
                     + "our end.");
            }
        }
        jQuery.ajax(
            { url: "username.json"
            , type: "POST"
            , success: success
            , dataType: 'json'
            , data: { username: username }
            , success: success
            , error: error
             }
        );
        return false;
    });
    $('.username BUTTON.cancel').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_username();
        return false;
    });
    function finish_editing_username()
    {
        $('.username BUTTON.edit').show();
        $('.username BUTTON.save').hide();
        $('.username BUTTON.cancel').hide();
        $('.username SPAN.view').show();
        $('.username INPUT').hide();
        $('.username .warning').hide();
    }


    // Wire up chosen box for communities.
    // ===================================

    var communityChooser = $('.communities SELECT')
    var communityList = $('.communities UL')

    function createOption(term)
    {
        Gittip.communities.join(term, updateDOM);
    }

    function updateDOM(data)
    {
        var itms = '';
        var opts = '<option></option>'; // per Chosen docs, to get placeholder
        for (var i=0, community; community = data.communities[i]; i++)
        {
            if (community.is_member)
            {
                var nothers = (community.nmembers - 1);
                itms += '<li data-slug="' + community.slug + '">'
                      + '<a href="/for/' + community.slug + '/">'
                      + community.name
                      + '</a>'
                      + '<div class="fine">with '
                      + nothers
                      + ' other' + (nothers === 1?'':'s')
                      + ' | ' + '<span class="leave">leave</span>'
                      + '</div>'
                      + '</li>';
            } else {
                var nneeded = data.threshold - community.nmembers;
                opts += '<option value="' + community.name + '">'
                      + community.name + ' - ' + community.nmembers
                      + ' member' + ((community.nmembers === 1) ? '' : 's')
                      + (nneeded > 0 ? ' - ' + nneeded + ' more needed' : '')
                      + '</option>';
            }
        }
        communityList.html(itms);
        communityChooser.html(opts).trigger('liszt:updated');
        $('.leave', communityList).click(function()
        {
            var name = $('a', $(this).closest('li')).text();
            Gittip.communities.leave(name, updateDOM);
        });
    }

    var chosenOpts = { create_option: createOption
                     , create_option_text: "Add a new community"
                      };
    communityChooser.chosen(chosenOpts).change(function() {
        Gittip.communities.join(communityChooser.val(), updateDOM);
    });

    jQuery.get('/for/communities.json', updateDOM);


    // Wire up textarea for statement.
    // ===============================

    $('TEXTAREA').focus();
    function start_editing_statement()
    {
        var h = $('.statement DIV.view').height();
        h = Math.max(h, 128);
        $('.statement TEXTAREA').height(h);

        $('.statement BUTTON.edit').hide();
        $('.statement BUTTON.save').show();
        $('.statement BUTTON.cancel').show();
        $('.statement DIV.view').hide();
        $('.statement DIV.edit').show(0, function() {
            $('.statement TEXTAREA').focus();
        });
    }
    if ($('.statement TEXTAREA').val() === '')
    {
        start_editing_statement();
    }
    $('.statement BUTTON.edit').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        start_editing_statement();
        return false;
    });
    $('FORM.statement').submit(function(e)
    {
        e.preventDefault();

        $('.statement BUTTON.save').text('Saving ...');

        function success(d)
        {
            $('.statement .view SPAN').html(d.statement);
            var number = $('.statement SELECT').val();
            Gittip.profile.toNumber(number);
            finish_editing_statement();
        }
        jQuery.ajax(
            { url: "statement.json"
            , type: "POST"
            , success: success
            , data: { statement: $('.statement TEXTAREA').val()
                    , number: $('.statement SELECT').val()
                     }
             }
        )
        return false;
    });
    $('.statement BUTTON.cancel').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_statement();
        return false;
    });
    function finish_editing_statement()
    {
        $('.statement BUTTON.edit').show();
        $('.statement BUTTON.save').hide().text('Save');
        $('.statement BUTTON.cancel').hide();
        $('.statement DIV.view').show();
        $('.statement DIV.edit').hide();
        $('.statement .warning').hide();
    }


    // Wire up goal knob.
    // ==================

    $('.goal BUTTON.edit').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        $('.goal DIV.view').hide();
        $('.goal TABLE.edit').show();
        $('.goal BUTTON.edit').hide();
        $('.goal BUTTON.save').show();
        $('.goal BUTTON.cancel').show();
        return false;
    });
    $('FORM.goal').submit(function(e)
    {
        e.preventDefault();

        $('.goal BUTTON.save').text('Saving ...');

        var goal = $('INPUT[name=goal]:checked');

        function success(d)
        {
            var label = $('LABEL[for=' + goal.attr('id') + ']');
            var newtext = '';
            if (label.length === 1)
                newtext = label.html();
            else
            {   // custom goal is wonky
                newtext = label.html();
                newtext = newtext.replace('$', '$' + d.goal);
                newtext += $(label.get(1)).html();
            }

            if (parseFloat(d.goal) > 0)
                $('INPUT[name=goal_custom]').val(d.goal);
            $('.goal DIV.view').html(newtext);
            finish_editing_goal();
        }
        jQuery.ajax(
            { url: "goal.json"
            , type: "POST"
            , success: success
            , dataType: 'json'
            , data: { goal: goal.val()
                    , goal_custom: $('[name=goal_custom]').val()
                     }
            , success: success
            , error: function() {
                    $('.goal BUTTON.save').text('Save');
                    alert( "Failed to change your funding goal. "
                         + "Please try again."
                          );
                }
             }
        );
        return false;
    });
    $('.goal BUTTON.cancel').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_goal();
        return false;
    });
    function finish_editing_goal()
    {
        $('.goal DIV.view').show();
        $('.goal TABLE.edit').hide();
        $('.goal BUTTON.edit').show();
        $('.goal BUTTON.save').hide().text('Save');;
        $('.goal BUTTON.cancel').hide();
    }


    // Wire up aggregate giving knob.
    // ==============================

    $('.anonymous INPUT').click(function()
    {
        jQuery.ajax(
            { url: 'anonymous.json'
            , type: 'POST'
            , dataType: 'json'
            , success: function(data)
            {
                $('.anonymous INPUT').attr('checked', data.anonymous);
            }
            , error: function() {
                    alert( "Failed to change your anonymity "
                         + "preference. Please try again."
                          );
                }
             }
        );
    });


    // Wire up API Key
    // ===============
    //
    function hit_api_key(method)
    {
        return function()
        {
            jQuery.ajax(
                { url: 'api-key.json'
                , type: method
                , dataType: 'json'
                , data: {action: 'show'}
                , success: function(d)
                {
                    $('.api-key span').text(d.api_key);
                }
                 }
            );
        }
    }

    $('.api-key .show').click(hit_api_key('GET'));
    $('.api-key .hide').click(function()
    {
        $('.api-key span').text('xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx');
    });
    $('.api-key .recreate').click(hit_api_key('POST'));
});
