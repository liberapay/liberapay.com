Gittip.team = (function() {
    function init() {
        $('#lookup-container form').submit(add);
        $('#query').focus().keyup(lookup);
        jQuery.get("index.json").success(drawRows);
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
            rows.push(Gittip.jsonml(
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
                rows.push(Gittip.jsonml(
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
                rows.push(Gittip.jsonml(
                    [ 'tr'
                    , ['td']
                    , ['td']
                    , ['td']
                    , ['td']
                    , ['td', {'class': 'figure balance'}, num(member.take)]
                    , ['td', {'class': 'figure percentage'}, perc(member.percentage)]
                     ]
                ));
        }
        $('#members').html(rows);
        $('#take').submit(doTake);
        $('#take input').focus().keyup(maybeCancelTake);
        $('#members .remove').click(remove);
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
            items.push(Gittip.jsonml(
                ['li', {"data-id": result.id}, result.username]
            ));
        }
        $('#lookup-results').html(items);
    }

    function add(e) {
        e.preventDefault();
        e.stopPropagation();
        var query = $('#query').val();
        setTake(query, '0.01', function() { alert('Member added!'); });
        $('#lookup-results').empty();
        $('#query').val('').focus();
        return false;
    }

    function remove(e) {
        e.preventDefault();
        e.stopPropagation();
        var membername = $(e.target).attr('data-username');
        if (confirm("Remove " + membername + " from this team?"))
            setTake(membername, '0.00', function() { alert('Member removed!'); });
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
        var _ = $('#take input');
        _.val(_.attr('data-take')).blur();
    }

    function doTake(e) {
        e.preventDefault();
        e.stopPropagation();
        var frm = $('#take'), _ = $('input', frm);
        var username = _.attr('data-username'),
                take = _.val();
        if (take.search(/^\d+\.?\d*$/) !== 0)
            alert("Bad input! Must be a number.");
        else
        {
            var callback = function(d) {
                var newTake = $.grep(d, function(row) { return row.username == username })[0].take;
                if ( take == newTake)
                    alert('Updated your take!');
                else
                    alert('You cannot exceed double of last week. Updated your take to ' + newTake + '.');
            };
            if (parseFloat(take) === 0) {
                if (!confirm("Remove yourself from this team?")) {
                    resetTake();
                    return false;
                }
                callback = function() { alert('Removed!'); };
            }
            setTake(username, take, callback);
        }
        return false;
    }

    function setTake(username, take, callback) {
        callback = callback || function() {};

        // The members.json endpoint takes a list of member objects so that it
        // can be updated programmatically in bulk (as with tips.json. From
        // this UI we only ever change one at a time, however.

        jQuery.ajax(
                { type: 'POST'
                , url: username + ".json"
                , data: {take: take}
                , success: function(d) { callback(d); drawRows(d); }
                , error: function(xhr) {
                        switch (xhr.status) {
                            case 404: alert("Unknown user!"); break;
                            default: alert("Problem! " + xhr.status);
                        }
                    }
                 });
    }


    // Export
    // ======

    return {init: init};
})();
