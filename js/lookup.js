Liberapay.lookup = {};

Liberapay.lookup.init = function() {
    $('form.username-lookup').each(function() {
        var $form = $(this);
        var $input = $form.find('input[name="username"]');
        var $results = $form.find('.lookup-results');
        $results.css('width', $input.css('width'));

        var lookup_timeout = null;
        function lookup() {
            if (lookup_timeout) clearTimeout(lookup_timeout);
            var query = $(this).val();
            if (query.length < 3)
                $results.empty();
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
            $results.html(items);
        }

        function selectLookupResult() {
            $input.val($(this).html()).focus();
            $results.empty();
        }

        $results.on('click', 'li', selectLookupResult);
        $input.keyup(lookup);
    });
};
