var GratipayWidget0001 = {};


GratipayWidget0001.create_element = function(el_type, ident, opts)
{
    var id = "autoloaded-" + ident;
    if (document.getElementById(id))
        return;

    var el = document.createElement(el_type);
    el.id = id;
    for (var key in opts) {
        el[key] = opts[key];
    }
    document.getElementsByTagName('head')[0].appendChild(el);
};


GratipayWidget0001.setup = function()
{
    // Get the script element and compute a CSS file to load.

    var script = document.getElementById('gratipay-0001')
      , cssURI = script.src.replace(/.js$/, '.css')
      , base = script.src.slice(0, 4) === 'http'
             ? script.src.replace(/^(https?:\/\/[^/]+).*$/, '$1')
             : ''
      , jQueryURI = base + '/assets/jquery-1.7.1.min.js'
       ;

    this.base = base;


    // Load the CSS file. (We need this even if the page already has jQuery.)

    GratipayWidget0001.create_element( 'link'
                                   , 'widget'
                                   , { 'href': cssURI
                                     , 'type': 'text/css'
                                     , 'rel': 'stylesheet'
                                      }
                                    );


    // Load jQuery, and block until it loads.

    if (!('jQuery' in window))
    {
        GratipayWidget0001.create_element( 'script'
                                       , 'jquery'
                                       , { 'src': jQueryURI
                                         , 'type': 'text/javascript'
                                          }
                                        );
        setTimeout(GratipayWidget0001.setup, 50);
        return;
    }


    // Once jQuery is loaded, proceed.

    $('span.gratipay-0001[gratipay-username]').each(GratipayWidget0001.setupOneWidget);
};


GratipayWidget0001.setupOneWidget = function()
{
    var DEFAULT = '0.00';

    var span = $(this)
      , username = span.attr('gratipay-username')
      , base = GratipayWidget0001.base;
       ;

    function updateWidget(a, b, c)
    {
        var receiving = $('[gratipay-username=' + username + '] .receiving');
        receiving.text(a.receiving || DEFAULT);
    }

    function startUpdatingWidget()
    {
        var uri = GratipayWidget0001.base + '/' + username + '/public.json'
        jQuery.ajax({ 'url': uri
                    , 'type': 'GET'
                    , 'dataType': 'json'
                    , 'success': updateWidget
                    , 'error': updateWidget
                     });
    }

    $(document).ready(function()
    {
        span.append( '<span class="gratipay-0001-padding">I receive<br/>'
                   + '<b><a href="' + base + '/' + username + '/">'
                   + '$<span class="receiving">' + DEFAULT + '</span></b>'
                   + ' / wk</a><br />'
                   + 'on <a href="' + base + '/">Gratipay</a>.</span>')
        startUpdatingWidget();
    });
};

GratipayWidget0001.setup();
