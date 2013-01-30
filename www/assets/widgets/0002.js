(function($, _) {
	var s        = $('script'),
	    script   = s[s.length - 1],
	    baseURI  = script.getAttribute('data-gittip-base')
	            || script.src.replace(/^((https?:)?\/\/[^\/]+).*$/, '$1'),
	    username = script.getAttribute('data-gittip-username'),
	    widget, receiving;

	// include css
	$('head')[0].appendChild(
		_.ml(['link', {
			rel: 'stylesheet',
			href: script.src.replace('.js', '.css').replace(/\?.+/, '')
		}])
	);

	// set up widget
	script.parentNode.insertBefore(_.ml(
		['div', { 'class': 'gittip-widget gittip-0002' },
			[ 'div', { 'class': 'gittip-inner' },
				'I receive ', ['br'],
				['a', { href: baseURI + '/' + username + '/' },
					[ 'b', '$', receiving = _.ml(['span', '0.00'])] , ' / wk'
				],
				['br'],
				' on ', ['a', { href: baseURI }, 'Gittip' ], '.'
			]
		]
	), script);

	// display current receiving value
	_.json(baseURI + '/' + username + '/public.json', function(data) {
		receiving.innerHTML = data.receiving;
	});
})(function(q) { return document.querySelectorAll(q); }, {
	ml: function(jsonml) {
		var i, p, v, node;

		node = document.createElement(jsonml[0]);

		for (i=1; i<jsonml.length; i++) {
			v = jsonml[i];

			switch (v.constructor) {
				case Object:
					for (p in v)
						node.setAttribute(p, v[p]);
					break;

				case Array: node.appendChild(this.ml(v)); break;

				case String: case Number:
					node.appendChild(document.createTextNode(v));
					break;

				default: node.appendChild(v); break;
			}
		}

		return node;
	},

	_xhr: function(cb) {
		var xhr = new XMLHttpRequest();

		if (xhr.withCredentials == undefined && XDomainRequest)
			return this._xdr(cb);

		xhr.onreadystatechange = function() {
			if (xhr.readyState == 4 && xhr.status == 200) cb();
		};

		return xhr;
	},

	_xdr: function(cb) {
		var xdr = new XDomainRequest();
		xdr.onload = cb;
		return xdr;
	},

	json: function(url, cb) {
		var xhr = this._xhr(function() {
			cb(JSON.parse(xhr.responseText));
		});

		xhr.open('GET', url);
		xhr.send();
	}
});
