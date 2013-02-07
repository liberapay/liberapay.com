
$(document).ready(function()
{

    ////////////////////////////////////////////////////////////
    //                                                         /
    // XXX This is ripe for refactoring. I ran out of steam. :-/
    //                                                         /
    ////////////////////////////////////////////////////////////


    // Wire up participant_id knob.
    // ============================

    $('FORM.participant_id BUTTON.edit').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        $('.participant_id BUTTON.edit').hide();
        $('.participant_id BUTTON.save').show();
        $('.participant_id BUTTON.cancel').show();
        $('.participant_id SPAN.view').hide();
        $('.participant_id INPUT').show().focus();
        $('.participant_id .warning').show();
        return false;
    });
    $('FORM.participant_id').submit(function(e)
    {
        e.preventDefault();

        $('#save-participant_id').text('Saving ...');

        var participant_id = $('INPUT[name=participant_id]').val();

        function success(d)
        {
            window.location.href = "/" + encodeURIComponent(d.participant_id) + "/";
        }
        function error(e)
        {
            $('#save-participant_id').text('Save');
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
            { url: "participant_id.json"
            , type: "POST"
            , success: success
            , dataType: 'json'
            , data: { participant_id: participant_id }
            , success: success
            , error: error
             }
        );
        return false;
    });
    $('.participant_id BUTTON.cancel').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_participant_id();
        return false;
    });
    function finish_editing_participant_id()
    {
        $('.participant_id BUTTON.edit').show();
        $('.participant_id BUTTON.save').hide();
        $('.participant_id BUTTON.cancel').hide();
        $('.participant_id SPAN.view').show();
        $('.participant_id INPUT').hide();
        $('.participant_id .warning').hide();
    }


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
            finish_editing_statement();
        }
        jQuery.ajax(
            { url: "statement.json"
            , type: "POST"
            , success: success
            , data: {"statement": $('.statement TEXTAREA').val()}
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
            var newtext = $('LABEL[for=' + goal.attr('id') + ']').text();
            newtext = newtext.replace('$', '$' + d.goal);

            if (d.goal !== '0.00')
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
                    $('#save-goal').text('Save');
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

    $('.anonymous').click(function()
    {
        jQuery.ajax(
            { url: 'anonymous.json'
            , type: 'POST'
            , dataType: 'json'
            , success: function(data)
            {
                $('INPUT.anonymous').attr('checked', data.anonymous);
            }
            , error: function() {
                    alert( "Failed to change your anonymity "
                         + "preference. Please try again."
                          );
                }
             }
        );
    });
});
