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
	SHARED_DATABASE_URL="postgres://postgres:jesus@localhost:5432/logstown" \
	SAMURAI_MERCHANT_KEY="7b79175baca336eaf4bfe8c8" \
	SAMURAI_MERCHANT_PASSWORD="3d6b8ad3b16d8c538c9189a0" \
	SAMURAI_PROCESSOR_TOKEN="4620d34456c7de7bab7f3a13" \
	SAMURAI_SANDBOX="true" \
	CANONICAL_HOST=localhost \
	CANONICAL_SCHEME=http \
		sudo -E ./env/bin/thrash ./env/bin/aspen -vDEBUG -a:80 www/
