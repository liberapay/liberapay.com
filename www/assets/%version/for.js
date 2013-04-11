Gittip.for = angular.module('Gittip.for', []);

Gittip.for.DesertsCtrl = function($scope, $http)
{
    $scope.fetch = function()
    {
        if ($scope.query == '')
            $scope.lookup = [];
        else
            $http.get("/for/lookup.json", {params: {query: $scope.query}})
                 .success(function(data) { $scope.lookup = data });
    };

    // No good way in Angular yet:
    // http://stackoverflow.com/questions/14833326/
    jQuery('#query').focus();
};
