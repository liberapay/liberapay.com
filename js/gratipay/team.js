Gratipay.team = (function() {
    function init() {
        $('#lookup-container form').submit(add);
        $('#lookup-results').on('click', 'li', selectLookupResult);
        $('#query').focus().keyup(lookup);

        jQuery.get("index.json").success(function(members) {
            $('.loading-indicator').remove();
            drawRows(members);
        });
    }


    // Draw Rows
    // =========

    function num(n) { return n.toFixed(2); }
    function perc(n) { return (n * 100).toFixed(1); }

    function drawMemberTake(member) {
        var take = num(member.take);

        if (member.editing_allowed)
            return [ 'form', {'id': 'take'}
                         , ['input', { 'value': take
                                                 , 'data-username': member.username
                                                 , 'data-take': take // useful to reset form
                                                 , 'tabindex': '1'
                                                    }]
                            ];

        if (member.removal_allowed)
            return [ 'span', { 'class': 'remove'
                                             , 'data-username': member.username
                                                }, take];

        return take;
    }

    function drawRows(members) {
        nmembers = members.length - 1; // includes the team itself, which we don't
                                       // want to enumerate
        var rows = [];

        if (nmembers === 0) {
            rows.push(Gratipay.jsonml(
                [ 'tr'
                , ['td', {'colspan': '6', 'class': 'no-members'}, "No members"]
                 ]
            ));
        }

        for (var i=0, len=members.length; i<len; i++) {
            var member = members[i];
            var increase = '';

            if (member.take > member.last_week)
                increase = 'moderate';
            if (member.take > (member.last_week * 1.25))
                increase = 'high';
            if (member.take === member.max_this_week)
                increase = 'max';

            if (i < nmembers)
                rows.push(Gratipay.jsonml(
                    [ 'tr'
                    , ['td', {'class': 'n'}, (i === nmembers ? '' : nmembers - i)]
                    , ['td', ['a', {'href': '/'+member.username+'/'}, member.username]]
                    , ['td', {'class': 'figure last_week'}, num(member.last_week)]
                    , ['td', {'class': 'figure take ' + increase}, drawMemberTake(member)]
                    , ['td', {'class': 'figure balance'}, num(member.balance)]
                    , ['td', {'class': 'figure percentage'}, perc(member.percentage)]
                     ]
                ));
            else if (nmembers > 0)
                rows.push(Gratipay.jsonml(
                    [ 'tr'
                    , ['td']
                    , ['td']
                    , ['td']
                    , ['td', {'class': 'figure take'}, num(member.take)]
                    , ['td', {'class': 'figure balance'}, num(member.balance)]
                    , ['td', {'class': 'figure percentage'}, perc(member.percentage)]
                     ]
                ));
        }
        $('#team-members').html(rows);
        $('#take').submit(doTake);
        $('#take input').focus().keyup(maybeCancelTake);
        $('#team-members .remove').click(remove);
    }


    // Add
    // ===

    function lookup() {
        var query = $('#query').val();
        if (query === '')
            $('#lookup-results').empty();
        else
            jQuery.get("/lookup.json", {query: query}).success(drawLookupResults);
    }

    function drawLookupResults(results) {
        var items = [];
        for (var i=0, len=results.length; i<len; i++) {
            var result = results[i];
            items.push(Gratipay.jsonml(
                ['li', {"data-id": result.id}, result.username]
            ));
        }
        $('#lookup-results').html(items);
    }

    function selectLookupResult() {
        $('#query').val($(this).html());
        $('#lookup-results').empty();
    }

    function add(e) {
        e.preventDefault();
        e.stopPropagation();
        var query = $('#query').val();
        setTake(query, '0.01');
        $('#lookup-results').empty();
        $('#query').val('').focus();
        return false;
    }

    function remove(e) {
        e.preventDefault();
        e.stopPropagation();
        var membername = $(e.target).attr('data-username');
        setTake(membername, '0.00');
        return false;
    }


    // Take
    // ====

    function maybeCancelTake(e) {
        if (e.which === 27) {
            resetTake();
        }
    }

    function resetTake() {
        $('#take').show().parent().find('.updating').remove();
        var _ = $('#take input');
        _.val(_.attr('data-take')).blur();
    }

    function doTake(e) {
        e.preventDefault();
        e.stopPropagation();
        var frm = $('#take'), _ = $('input', frm);
        var username = _.attr('data-username'),
                take = _.val();
        setTake(username, take);
        return false;
    }

    function setTake(username, take, confirmed) {
        if ($('#take').parent().find('.updating').length === 0) {
            var $updating = $('<span class="updating"></span>');
            $updating.text($('#team').data('updating'));
            $('#take').hide().parent().append($updating);
        }

        var data = {take: take};
        if (confirmed) data.confirmed = true;

        jQuery.ajax(
                { type: 'POST'
                , url: username + ".json"
                , data: data
                , success: function(d) {
                    if (d.confirm) {
                        if (confirm(d.confirm)) {
                            return setTake(username, take, true)
                        } else {
                            return resetTake()
                        }
                    }
                    if(d.success) {
                        Gratipay.notification(d.success, 'success');
                    }
                    drawRows(d.members);
                }
                , error: [resetTake, Gratipay.error]
                 });
    }


    // Export
    // ======

    return {init: init};
})();
