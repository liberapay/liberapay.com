Gittip.for = angular.module('Gittip.for', []);

Gittip.for.DesertsCtrl = function($scope, $http)
{
    $scope.fetch = function()
    {
        if ($scope.query == '')
            $scope.participants = [];
        if ($scope.query.length < 2)
            return;
        $http.get("/for/_lookup.json", {params: {query: $scope.query}})
             .success(function(data) { $scope.participants = data });
    };
};
