Gittip.open_group = angular.module('Gittip.open_group', []);

Gittip.open_group.IdentificationsCtrl = function($scope, $http)
{
    $scope.weights = [0, 1, 6, 12, 25, 50, 100];

    function updateMembers(data)
    {
        $scope.identifications = data.identifications;
        var split = data.split;
        $scope.nanswers = split[0];
        $scope.nanswers_threshold = split[1];
        $scope.nanswers_needed = split[1] - split[0];
        $scope.split = split[2];
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
        $scope.change({'username': $scope.query}, $scope.weights[1]);
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
        $http.post("members.json", data, config)
             .success(updateMembers);
    };

    $http.get("members.json").success(updateMembers);

    // No good way in Angular yet:
    // http://stackoverflow.com/questions/14833326/
    jQuery('#query').focus();
};


// :cry: Conditionals are a third-party thing. :/
// http://stackoverflow.com/questions/14077471/
// https://github.com/angular-ui/angular-ui/blob/31f82eaec5f07224b2a57607089ce8f8acffd48c/modules/directives/if/if.js

/*
 * Defines the ui-if tag. This removes/adds an element from the dom depending on a condition
 * Originally created by @tigbro, for the @jquery-mobile-angular-adapter
 * https://github.com/tigbro/jquery-mobile-angular-adapter
 */

Gittip.open_group.directive('uiIf', [function () {
  return {
    transclude: 'element',
    priority: 1000,
    terminal: true,
    restrict: 'A',
    compile: function (element, attr, transclude) {
      return function (scope, element, attr) {

        var childElement;
        var childScope;

        scope.$watch(attr['uiIf'], function (newValue) {
          if (childElement) {
            childElement.remove();
            childElement = undefined;
          }
          if (childScope) {
            childScope.$destroy();
            childScope = undefined;
          }

          if (newValue) {
            childScope = scope.$new();
            transclude(childScope, function (clone) {
              childElement = clone;
              element.after(clone);
            });
          }
        });
      };
    }
  };
}]);
