Liberapay.team = (function() {
    function init() {
        $('#lookup-results').on('click', 'li', selectLookupResult);
        $('#query').keyup(lookup);
    }

    var lookup_timeout = null;
    var $query = $('#query');
    function lookup() {
        if (lookup_timeout) clearTimeout(lookup_timeout);
        var query = $query.val();
        if (query.length < 3)
            $('#lookup-results').empty();
        else {
            lookup_timeout = setTimeout(function() {
                jQuery.get("/search.json", {scope: 'usernames', q: query}).success(drawLookupResults);
            }, 300);
        }
    }

    function drawLookupResults(results) {
        var items = [];
        var results = results.usernames;
        for (var i=0, len=results.length; i<len; i++) {
            var result = results[i];
            items.push(Liberapay.jsonml(
                ['li', {"data-id": result.id}, result.username]
            ));
        }
        $('#lookup-results').html(items);
    }

    function selectLookupResult() {
        $('#query').val($(this).html());
        $('#lookup-results').empty();
    }

    return {init: init};
})();
