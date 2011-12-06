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
	SHARED_DATABASE_URL="postgres://postgres:jesus@localhost:5432/logstown" sudo -E ./env/bin/thrash ./env/bin/aspen -vDEBUG -a:80 www/
