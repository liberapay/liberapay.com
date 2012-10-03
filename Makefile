env:
	python2.7 ./vendor/virtualenv-1.7.1.2.py \
				--unzip-setuptools \
				--prompt="[gittip] " \
				--never-download \
				--extra-search-dir=./vendor/ \
				--distribute \
				./env/
	./env/bin/pip install -r requirements.txt
	./env/bin/pip install ./vendor/nose-1.1.2.tar.gz
	./env/bin/pip install -e ./


clean:
	rm -rf env *.egg *.egg-info
	find . -name \*.pyc -delete

run: env
	./env/bin/swaddle local.env ./env/bin/aspen \
		--www_root=www/ \
		--project_root=.. \
		--show_tracebacks=yes \
		--changes_reload=yes \
		--network_address=:8537

test: env tests/env data
	./env/bin/swaddle tests/env ./env/bin/nosetests ./tests/

tests/env:
	echo "Creating a tests/env file ..."
	echo
	echo "CANONICAL_HOST=localhost:8537" > tests/env
	echo "CANONICAL_SCHEME=http" >> tests/env
	echo "DATABASE_URL=postgres://gittip-test@localhost/gittip-test" >> tests/env
	echo "STRIPE_SECRET_API_KEY=1" >> tests/env
	echo "STRIPE_PUBLISHABLE_API_KEY=1" >> tests/env
	echo "BALANCED_API_SECRET=90bb3648ca0a11e1a977026ba7e239a9" >> tests/env
	echo "GITHUB_CLIENT_ID=3785a9ac30df99feeef5" >> tests/env
	echo "GITHUB_CLIENT_SECRET=e69825fafa163a0b0b6d2424c107a49333d46985" >> tests/env
	echo "GITHUB_CALLBACK=http://localhost:8537/github/associate" >> tests/env
	echo "TWITTER_CONSUMER_KEY=QBB9vEhxO4DFiieRF68zTA" >> tests/env
	echo "TWITTER_CONSUMER_SECRET=mUymh1hVMiQdMQbduQFYRi79EYYVeOZGrhj27H59H78" >> tests/env
	echo "TWITTER_CALLBACK=http://127.0.0.1:8537/on/twitter/associate" >> tests/env

data: env
	./makedb.sh gittip-test gittip-test
	./env/bin/swaddle tests/env ./env/bin/python ./gittip/testing.py
