Gittip.team = angular.module('Gittip.team', []);

Gittip.team.TeamCtrl = function($scope, $http)
{
    function updateMembers(data)
    {
        $scope.members = data;
    }

    $scope.isCurrentUser = function(member)
    {
        console.log(member.is_current_user, member);
        return member.is_current_user;
    };

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
        $scope.change({'username': $scope.query}, '0.01');
        $scope.lookup = [];
        $scope.query = '';
        jQuery('#query').focus();
    };

    var updateHandle = null;
    $scope.doUpdate = function()
    {
        clearTimeout(updateHandle);
        updateHandle = setTimeout(function()
        {
            if ($scope.take.search(/^\d+\.?\d*$/) !== 0)
                return;
            $scope.change($scope.member, $scope.take);
        }, 500);
    };

    $scope.change = function(participant, take)
    {

        // The members.json endpoint takes a list of member objects so that it
        // can be updated programmatically in bulk (as with tips.json. From
        // this UI we only ever change one at a time, however.

        var data = { take: take
                   , csrf_token: getCookie('csrf_token')
                    };
        // http://stackoverflow.com/questions/12190166/
        data = jQuery.param(data);
        var content_type = 'application/x-www-form-urlencoded; charset=UTF-8';
        var config = {headers: {'Content-Type': content_type}};
        $http.post(participant.username + ".json", data, config)
             .success(updateMembers);
    };

    $http.get("index.json").success(updateMembers);

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

Gittip.team.directive('uiIf', [function () {
    console.log('anything?');
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
