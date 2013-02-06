$(document).ready(function()
{
    // Wire up is_suspicious toggle.
    // =============================

    $('.is-suspicious-knob').click(function()
    {
        jQuery.ajax(
            { url: 'toggle-is-suspicious.json'
            , type: 'POST'
            , dataType: 'json'
            , success: function(data)
            {
                if (data.is_suspicious)
                    $("#their-voice").addClass('is-suspicious');
                else
                    $("#their-voice").removeClass('is-suspicious');
                $('INPUT.is-suspicious-knob').attr( 'checked'
                                                  , data.is_suspicious
                                                   );
            }
            , error: function() {
                    alert( "Failed to change is_suspicious. Please "
                         + "try again."
                          );
                }
             }
        );
    });
});
