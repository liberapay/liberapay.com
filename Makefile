env:
	python2.7 ./vendor/virtualenv-1.6.4.py \
				--no-site-packages \
				--unzip-setuptools \
				--prompt="[logstown] " \
				--never-download \
				--extra-search-dir=./vendor/ \
				--distribute \
				./env/
	./env/bin/pip install -r requirements.txt

clean:
	rm -rf env

run: env
	sudo ./env/bin/thrash ./env/bin/aspen -vDEBUG -a:80www/
