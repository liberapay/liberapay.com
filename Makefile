python := "$(shell { command -v python2.7 || command -v python; } 2>/dev/null)"

# Set the relative path to installed binaries under the project virtualenv.
# NOTE: Creating a virtualenv on Windows places binaries in the 'Scripts' directory.
bin_dir := $(shell $(python) -c 'import sys; bin = "Scripts" if sys.platform == "win32" else "bin"; print(bin)')
env_bin := env/$(bin_dir)
venv := "./vendor/virtualenv-1.9.1.py"

postgression_api_url := http://api.postgression.com/

define postgression_database
$(shell ./$(env_bin)/python -c '
import requests
response=requests.get("$(postgression_api_url)")
if response.status_code == 200:
	print "\"DATABASE_URL=%s\\n\"" % response.text
')
endef

env: $(env_bin)/swaddle
	$(python)  $(venv)\
				--unzip-setuptools \
				--prompt="[gittip] " \
				--never-download \
				--extra-search-dir=./vendor/ \
				--distribute \
				./env/
	./$(env_bin)/pip install -r requirements.txt
	./$(env_bin)/pip install -r requirements_tests.txt
	./$(env_bin)/pip install -e ./

$(env_bin)/swaddle:
	$(python) $(venv)\
				--unzip-setuptools \
				--prompt="[gittip] " \
				--never-download \
				--extra-search-dir=./vendor/ \
				--distribute \
				./env/
	./$(env_bin)/pip install -r requirements.txt
	./$(env_bin)/pip install -r requirements_tests.txt
	./$(env_bin)/pip install -e ./

clean:
	rm -rf env *.egg *.egg-info
	find . -name \*.pyc -delete

local.env:
	echo "Creating a local.env file ..."
	echo
	cp default_local.env local.env

cloud-db: env local.env
	echo -n $(postgression_database) >> local.env

schema: env local.env
	./$(env_bin)/swaddle local.env ./recreate-schema.sh

data:
	./$(env_bin)/swaddle local.env ./$(env_bin)/fake_data fake_data

db: cloud-db schema data

run: env local.env
	./$(env_bin)/swaddle local.env ./$(env_bin)/aspen \
		--www_root=www/ \
		--project_root=. \
		--show_tracebacks=yes \
		--changes_reload=yes \
		--network_address=:8537

test-cloud-db: env tests/env
	echo -n $(postgression_database) >> tests/env

test-schema: env tests/env
	./$(env_bin)/swaddle tests/env ./recreate-schema.sh

test-db: test-cloud-db test-schema

test: env tests/env test-schema
	./$(env_bin)/swaddle tests/env ./$(env_bin)/py.test ./tests/

retest: env tests/env
	./$(env_bin)/swaddle tests/env ./$(env_bin)/py.test ./tests/ --lf

tests: test

node_modules: package.json
	npm install
	@if [ -d node_modules ]; then touch node_modules; fi

jstest: node_modules
	./node_modules/.bin/grunt test

tests/env:
	echo "Creating a tests/env file ..."
	echo
	cp default_tests.env tests/env
