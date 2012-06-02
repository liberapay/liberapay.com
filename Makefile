env:
	python2.7 ./vendor/virtualenv-1.7.1.2.py \
				--unzip-setuptools \
				--prompt="[logstown] " \
				--never-download \
				--extra-search-dir=./vendor/ \
				--distribute \
				./env/
	./env/bin/pip install -r requirements.txt
	./env/bin/pip install -e ./

clean:
	rm -rf env *.egg *.egg-info
	find . -name \*.pyc -delete

run: env
	sudo ./swaddle local.env ./env/bin/aspen \
		--www_root=www/ \
		--project_root=.. \
		--show_tracebacks=yes \
		--changes_reload=yes \
		--network_address=:80
