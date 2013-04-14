Gittip.openco = angular.module('Gittip.openco', []);


Gittip.openco.IdentificationsCtrl = function($scope, $http)
{
    $scope.weights = [0, 0.1, 1, 2, 4, 8, 16];

    function updateIdentifications(data)
    {
        $scope.identifications = data.identifications;
        $scope.split = data.split;
    }

    $scope.doLookup = function()
    {
        if ($scope.query == '')
            $scope.lookup = [];
        else
            $http.get("/lookup.json", {params: {query: $scope.query}})
                 .success(function(data) { $scope.lookup = data; });
    };

    $scope.doAdd = function()
    {
        $scope.change({'username': $scope.query}, 0.1);
        $scope.lookup = [];
        $scope.query = '';
        jQuery('#query').focus();
    };

    $scope.change = function(participant, weight)
    {
        console.log("changing", participant.username, "to", weight);
        var data = { member: participant.username
                   , weight: weight
                   , csrf_token: Gittip.getCookie('csrf_token')
                    };
        // http://stackoverflow.com/questions/12190166/
        data = jQuery.param(data);
        var content_type = 'application/x-www-form-urlencoded; charset=UTF-8';
        var config = {headers: {'Content-Type': content_type}};
        $http.post("identifications.json", data, config)
             .success(updateIdentifications);
    };

    $http.get("identifications.json").success(updateIdentifications);

    // No good way in Angular yet:
    // http://stackoverflow.com/questions/14833326/
    jQuery('#query').focus();
};
