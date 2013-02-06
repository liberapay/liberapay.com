$(document).ready(function()
{
    // Wire up textarea for statement.
    // ===============================

    $('TEXTAREA').focus();
    $('#edit-statement').click(function()
    {
        var h = $('BLOCKQUOTE.statement').height() - 64;
        h = Math.max(h, 128);
        $('BLOCKQUOTE.statement').hide();
        $('FORM.statement TEXTAREA').height(h);
        $('FORM.statement').show();
    });
    $('FORM.statement').submit(function(e)
    {
        e.preventDefault();

        $('#save-statement').text('Saving ...');

        function success(d)
        {
            $('FORM.statement').hide();
            $('BLOCKQUOTE.statement SPAN').html(d.statement);
            $('BLOCKQUOTE.statement').show();
            $('#save-statement').text('Save');
        }
        jQuery.ajax(
            { url: "statement.json"
            , type: "POST"
            , success: success
            , data: {"statement": $('TEXTAREA').val()}
             }
        )
        return false;
    });
    $('#cancel-statement').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        $('FORM.statement').hide();
        $('BLOCKQUOTE.statement').show();
        return false;
    });


    // Wire up goal knob.
    // ==================

    $('BLOCKQUOTE.goal BUTTON').click(function()
    {
        $('BLOCKQUOTE.goal').hide();
        $('FORM.goal').show();
    });
    $('FORM.goal').submit(function(e)
    {
        e.preventDefault();

        $('#save-goal').text('Saving ...');

        var goal = $('INPUT[name=goal]:checked');

        function success(d)
        {
            var newtext = $('LABEL[for=' + goal.attr('id') + ']').text();
            newtext = newtext.replace('$', '$' + d.goal);

            $('FORM.goal').hide();
            if (d.goal !== '0.00')
                $('INPUT[name=goal_custom]').val(d.goal);
            $('BLOCKQUOTE.goal DIV').html(newtext);
            $('BLOCKQUOTE.goal').show();
            $('#save-goal').text('Save');
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
    $('#cancel-goal').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        $('FORM.goal').hide();
        $('BLOCKQUOTE.goal').show();
        return false;
    });


    // Wire up participant_id knob.
    // ============================

    $('H2 BUTTON').click(function()
    {
        $('B.participant_id').hide();
        $('#edit-participant_id').hide();
        $('SPAN.participant_id').show();
        $('SPAN.participant_id INPUT').focus();
        $('H2.first').addClass('editing');
    });
    $('SPAN.participant_id FORM').submit(function(e)
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
    $('#cancel-participant_id').click(function(e)
    {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_participant_id();
        return false;
    });
    function finish_editing_participant_id()
    {
        $('SPAN.participant_id').hide();
        $('B.participant_id').show();
        $('#edit-participant_id').show();
        $('H2.first').removeClass('editing');
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
